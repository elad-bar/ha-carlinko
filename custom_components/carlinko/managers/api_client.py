"""CarLinko HTTP API client: login, signing, vehicle fetch, remote control.

Signing recovered from libapp.so (Blutter): see docs/decompiled/secure_*_utils.dart.
  signature = base64(HMAC-SHA256(SIGN_KEY,
              jsonEncode(sortByKeyAsc({...params, timestamp}))))   # Dart jsonEncode = no spaces
Login = POST /user/login with a plaintext password body. The `v-data` header the app sends is
NOT validated by the server, so we omit it.

Must not import homeassistant. Credentials come from the caller (HA config entry or
engine CLI/.env); token + vehicle ids from CarlinkoStore.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

from ..common.consts import (
    AC_BOOLS,
    API_HOST_TMPL,
    CFG_BOOLS,
    DEFAULT_REGION,
    DEFAULT_SIGN_KEY,
    LOGIN_BODY_DEFAULTS,
    OK_CODE,
    ROOF_BOOLS,
    SEAT_CAPS,
    STALE_TOKEN_CODES,
    USER_AGENT,
    WIN_BOOLS,
    WS_HOST_TMPL,
)
from ..common.helpers import flag, flags, parse_control_cfg, partial_id, seat_max
from ..models.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)


def vehicle_id_of(veh: dict[str, Any] | None) -> str:
    """Stable id from a /user/vehicle row."""
    if not veh:
        return ""
    return str(veh.get("vehicleId") or veh.get("id") or "")


def device_sn_of(veh: dict[str, Any] | None) -> str:
    if not veh:
        return ""
    return str(veh.get("deviceSn") or veh.get("deviceSN") or "")


class ApiClient:
    """Signed CarLinko REST calls over an injected aiohttp ClientSession."""

    def __init__(self, email, password, region, store, session: aiohttp.ClientSession):
        self.email = (email or "").strip()
        self.password = password or ""
        self.region = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
        self.store = store
        self.session = session
        sk = store.data.get("sign_key") or DEFAULT_SIGN_KEY
        self.sign_key = sk.encode() if isinstance(sk, str) else sk
        self.api_base = API_HOST_TMPL.format(region=self.region)
        self.ws_url = WS_HOST_TMPL.format(region=self.region)
        self.token = (store.data.get("token") or "").strip()
        # Legacy single-vehicle fields (engine / first car).
        self.vehicle_id = str(store.data.get("vehicle_id") or "")
        self.device_sn = str(store.data.get("device_sn") or "")
        self._veh_list: list[dict[str, Any]] = []
        self._veh_by_id: dict[str, dict[str, Any]] = {}
        self._caps_by_id: dict[str, dict[str, Any]] = {}
        self._list_cache_t = 0.0

    def reload_ids_from_store(self):
        self.store.load()
        self.token = (self.store.data.get("token") or "").strip() or self.token
        self.vehicle_id = (
            str(self.store.data.get("vehicle_id") or "") or self.vehicle_id
        )
        self.device_sn = str(self.store.data.get("device_sn") or "") or self.device_sn
        sk = self.store.data.get("sign_key") or DEFAULT_SIGN_KEY
        self.sign_key = sk.encode() if isinstance(sk, str) else sk

    @staticmethod
    def now_ms():
        return str(int(time.time() * 1000))

    def sign(self, params):
        if not self.sign_key:
            raise RuntimeError("sign_key missing")
        m = {k: ("" if v is None else str(v)) for k, v in params.items()}
        ordered = {k: m[k] for k in sorted(m.keys())}
        msg = json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode()
        return base64.b64encode(
            hmac.new(self.sign_key, msg, hashlib.sha256).digest()
        ).decode()

    def headers_for(self, params, token=None):
        ts = self.now_ms()
        h = {
            "timestamp": ts,
            "signature": self.sign({**params, "timestamp": ts}),
            "user-agent": USER_AGENT,
            "language": "en",
        }
        tok = token if token is not None else self.token
        if tok:
            h["token"] = tok
        return h

    async def login(self):
        """Log in with credentials; persist token via CarlinkoStore."""
        if not self.email or not self.password:
            raise RuntimeError(
                "email / password missing — pass credentials to ApiClient "
                "(HA: config entry; engine: .env / CLI)"
            )
        body = {
            "account": self.email,
            "password": self.password,
            **LOGIN_BODY_DEFAULTS,
            "dateTime": self.now_ms(),
        }
        ts = self.now_ms()
        h = {
            "timestamp": ts,
            "signature": self.sign({**body, "timestamp": ts}),
            "user-agent": USER_AGENT,
            "content-type": "application/json",
            "language": "en",
        }
        async with self.session.post(
            self.api_base + "/user/login",
            json=body,
            headers=h,
            timeout=_HTTP_TIMEOUT,
        ) as r:
            d = await r.json()
        code = str(d.get("code"))
        if code != OK_CODE:
            _LOGGER.warning(f"login failed code={d.get('code')} msg={d.get('msg')}")
            raise AuthError(f"login failed: {d}")
        data = d.get("data") or {}
        token = data.get("token") if isinstance(data, dict) else data
        if not token:
            _LOGGER.warning(
                f"login ok but no token code={d.get('code')} msg={d.get('msg')}"
            )
            raise AuthError(f"login ok but no token in response: {d}")
        self.token = token
        self.store.set_token(token)
        _LOGGER.info(f"login ok region={self.region} api_base={self.api_base}")
        return token

    def _caps_from_vehicle(self, v: dict) -> dict:
        cfg = parse_control_cfg(v.get("vehicleControlConfig"))
        ac = cfg.get("A/C") or {}

        out = flags(cfg, CFG_BOOLS)
        out["gear"] = flag(ac, "HighLowGear")
        out["windows"] = flags(cfg, WIN_BOOLS)
        out["sunroof"] = flags(cfg, ROOF_BOOLS)
        out["ac"] = {
            **flags(ac, AC_BOOLS),
            "min": ac.get("SetTemperatureMin"),
            "max": ac.get("SetTemperatureMax"),
            "step": ac.get("TemperatureStepValue"),
        }
        out["seats"] = {oid: seat_max(ac, fkey, lkey) for oid, fkey, lkey in SEAT_CAPS}
        out["plate"] = v.get("licenseNumber") or ""
        return out

    def _index_vehicles(self, rows: list[dict[str, Any]]) -> None:
        self._veh_list = list(rows)
        self._veh_by_id = {}
        self._caps_by_id = {}
        for row in rows:
            vid = vehicle_id_of(row)
            if not vid:
                continue
            self._veh_by_id[vid] = row
            try:
                self._caps_by_id[vid] = self._caps_from_vehicle(row)
            except Exception:
                _LOGGER.warning(
                    f"failed to parse vehicleControlConfig for vehicle={partial_id(vid)}",
                    exc_info=True,
                )
                self._caps_by_id[vid] = {}
        self._list_cache_t = time.time()
        if rows:
            _LOGGER.debug(f"indexed vehicleControlConfig for {len(rows)} vehicle(s)")
        # Keep legacy single-vehicle pointers for engine / first car.
        first = rows[0] if rows else {}
        vid0 = vehicle_id_of(first)
        dsn0 = device_sn_of(first)
        if vid0:
            self.vehicle_id = vid0
        if dsn0:
            self.device_sn = dsn0

    async def async_list_vehicles(self, force: bool = False) -> list[dict[str, Any]]:
        """Fetch full /user/vehicle list and refresh per-vehicle caps (~1h TTL)."""
        if not force and self._veh_list and (time.time() - self._list_cache_t) < 3600:
            return list(self._veh_list)

        async def _fetch(tok):
            _LOGGER.debug("GET /user/vehicle")
            async with self.session.get(
                self.api_base + "/user/vehicle",
                headers=self.headers_for({}, token=tok),
                timeout=_HTTP_TIMEOUT,
            ) as r:
                return await r.json()

        tok = self.token
        if not tok:
            tok = await self.login()
        d = await _fetch(tok)
        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug("stale token on /user/vehicle; re-login and retry")
            d = await _fetch(await self.login())
        code = str(d.get("code"))
        if code != OK_CODE:
            _LOGGER.warning(
                f"/user/vehicle failed code={d.get('code')} msg={d.get('msg')}"
            )
        data = d.get("data")
        if isinstance(data, list):
            rows = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            rows = [data]
        else:
            rows = []
        if not rows and code == OK_CODE:
            _LOGGER.warning("/user/vehicle returned no vehicles")
        self._index_vehicles(rows)
        if rows:
            _LOGGER.info(f"vehicle list refreshed count={len(rows)}")
        return list(self._veh_list)

    async def refresh_vehicle_cache(self, force=False, vehicle_id: str | None = None):
        """Fetch vehicles; return one row (selected id, else first). Engine-compatible."""
        rows = await self.async_list_vehicles(force=force)
        if vehicle_id:
            v = self._veh_by_id.get(str(vehicle_id)) or {}
        else:
            v = rows[0] if rows else {}
        return v or {}

    def get_vehicle(self, vehicle_id: str | None = None) -> dict[str, Any]:
        vid = str(vehicle_id or self.vehicle_id or "")
        return dict(self._veh_by_id.get(vid) or {})

    def control_caps(self, vehicle_id: str | None = None):
        """Capabilities from cached vehicle data (no network)."""
        vid = str(vehicle_id or self.vehicle_id or "")
        if vid and vid in self._caps_by_id:
            return dict(self._caps_by_id[vid])
        if not vid and self._caps_by_id:
            first = next(iter(self._caps_by_id.values()))
            return dict(first)
        return {}

    async def send_control(
        self,
        opcode,
        timeout=20,
        *,
        vehicle_id: str | None = None,
        device_sn: str | None = None,
    ):
        """POST /user/vehicle/remoteControl."""
        self.reload_ids_from_store()
        vid = str(vehicle_id or self.vehicle_id or "")
        dsn = str(device_sn or "")
        if not dsn and vid:
            meta = (
                self.store.get_vehicle_meta(vid)
                if hasattr(self.store, "get_vehicle_meta")
                else {}
            )
            dsn = str(meta.get("device_sn") or "") or device_sn_of(
                self._veh_by_id.get(vid)
            )
        if not dsn:
            dsn = self.device_sn
        if not vid or not dsn:
            _LOGGER.warning("remoteControl skipped vehicle_id/device_sn missing")
            return {"code": "-1", "msg": "vehicle_id / device_sn missing from store"}
        try:
            timeout = int(timeout)
        except Exception:
            timeout = 20
        body = {
            "vehicleId": vid,
            "deviceSn": dsn,
            "data": str(opcode),
            "timeOut": timeout,
        }
        post_timeout = aiohttp.ClientTimeout(total=timeout + 8)

        async def _post(tok):
            ts = self.now_ms()
            ordered = dict(sorted({**body, "timestamp": ts}.items()))
            msg = json.dumps(
                ordered, separators=(",", ":"), ensure_ascii=False
            ).encode()
            sig = base64.b64encode(
                hmac.new(self.sign_key, msg, hashlib.sha256).digest()
            ).decode()
            h = {
                "timestamp": ts,
                "signature": sig,
                "user-agent": USER_AGENT,
                "content-type": "application/json",
                "language": "en",
                "token": tok,
            }
            async with self.session.post(
                self.api_base + "/user/vehicle/remoteControl",
                data=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
                headers=h,
                timeout=post_timeout,
            ) as r:
                return await r.json()

        tok = self.token
        if not tok:
            tok = await self.login()
        _LOGGER.debug("POST /user/vehicle/remoteControl")
        d = await _post(tok)
        if str(d.get("code")) in STALE_TOKEN_CODES:
            _LOGGER.debug("stale token on remoteControl; re-login and retry")
            d = await _post(await self.login())
        code = str(d.get("code") or "")
        _LOGGER.info(
            f"remoteControl opcode={opcode} vehicle={partial_id(vid)} "
            f"code={d.get('code')}"
        )
        if code and code not in (OK_CODE, "0"):
            _LOGGER.warning(
                f"remoteControl failed opcode={opcode} vehicle={partial_id(vid)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
        return d
