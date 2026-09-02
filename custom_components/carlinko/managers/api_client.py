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
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
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
    API_VERSION,
    CFG_BOOLS,
    DEFAULT_REGION,
    DEFAULT_SIGN_KEY,
    LOCATION_UNSUPPORTED_CODES,
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
_QUERY_SKIP_PATHS = frozenset({"/user/login", "/user/vehicle/remoteControl"})
_ACCOUNT_QUERY_KEYS = frozenset({"GET /pub/timestamp", "GET /user/vehicle"})


def vehicle_id_of(veh: dict[str, Any] | None) -> str:
    """Stable id from a /user/vehicle row (``vehicleId``)."""
    if not veh:
        return ""

    return str(veh.get("vehicleId") or "")


def device_sn_of(veh: dict[str, Any] | None) -> str:
    """Device serial from a /user/vehicle row (``deviceId``)."""
    if not veh:
        return ""

    return str(veh.get("deviceId") or "")


def meta_from_api_row(veh: dict[str, Any]) -> dict[str, Any]:
    """Persistable per-vehicle meta from a /user/vehicle row."""
    vid = vehicle_id_of(veh)
    return {
        "vehicle_id": vid,
        "device_sn": device_sn_of(veh),
        "plate": veh.get("licenseNumber") or veh.get("plate") or "—",
        "model": veh.get("model")
        or veh.get("modelName")
        or veh.get("oldModel")
        or "EV",
        "vin": veh.get("vin") or veh.get("VIN") or "—",
    }


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

        self._veh_list: list[dict[str, Any]] = []
        self._veh_by_id: dict[str, dict[str, Any]] = {}
        self._caps_by_id: dict[str, dict[str, Any]] = {}
        self._list_cache_t = 0.0
        self._time_skew_ms = 0
        self._query_account: dict[str, dict[str, Any]] = {}
        self._query_vehicles: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def time_skew_ms(self) -> int:
        return int(self._time_skew_ms)

    def _vehicle_id_for_sn(self, device_sn: str) -> str:
        sn = str(device_sn or "").strip()
        if not sn:
            return ""
        if hasattr(self.store, "get_vehicles"):
            try:
                vehicles = self.store.get_vehicles() or {}
            except Exception:
                vehicles = {}
            if isinstance(vehicles, dict):
                for vid, meta in vehicles.items():
                    if str((meta or {}).get("device_sn") or "").strip() == sn:
                        return str(vid)
        for vid, row in self._veh_by_id.items():
            if device_sn_of(row) == sn:
                return str(vid)
        return ""

    def _record_query(
        self,
        *,
        method: str,
        path: str,
        started_at: str,
        finished_at: str,
        http_status: int | None,
        body: dict[str, Any] | None,
        error: str | None,
        log_vehicle_id: str | None = None,
    ) -> None:
        if path in _QUERY_SKIP_PATHS:
            return
        key = f"{method} {path}"
        cloud_code = None
        cloud_msg = None
        if isinstance(body, dict):
            if body.get("code") is not None:
                cloud_code = str(body.get("code"))
            cloud_msg = body.get("msg")
        record = {
            "request": {
                "started_at": started_at,
                "finished_at": finished_at,
                "http_status": http_status,
                "cloud_code": cloud_code,
                "cloud_msg": cloud_msg,
                "error": error,
            },
            "response": dict(body) if isinstance(body, dict) else None,
        }
        if key in _ACCOUNT_QUERY_KEYS:
            self._query_account[key] = record
            return
        vid = str(log_vehicle_id or "").strip()
        if not vid:
            return
        self._query_vehicles.setdefault(vid, {})[key] = record

    def query_log_for_diagnostics(
        self, vehicle_id: str | None = None
    ) -> dict[str, Any]:
        """Last query snapshots for diagnostics (account + per-vehicle)."""
        account = {k: dict(v) for k, v in self._query_account.items()}
        if vehicle_id:
            vid = str(vehicle_id)
            per = self._query_vehicles.get(vid) or {}
            return {"account": account, "vehicles": {vid: dict(per)}}
        vehicles = {vid: dict(bucket) for vid, bucket in self._query_vehicles.items()}
        return {"account": account, "vehicles": vehicles}

    def reload_ids_from_store(self):
        """Reload token / sign_key from store (not per-vehicle ids)."""
        self.store.load()

        self.token = (self.store.data.get("token") or "").strip() or self.token

        sk = self.store.data.get("sign_key") or DEFAULT_SIGN_KEY
        self.sign_key = sk.encode() if isinstance(sk, str) else sk

    def ids_for(self, vehicle_id: str) -> tuple[str, str]:
        """Resolve ``(vehicle_id, device_sn)`` for one car — never another car's SN."""
        vid = str(vehicle_id or "").strip()
        if not vid:
            return "", ""

        meta: dict[str, Any] = {}
        if hasattr(self.store, "get_vehicle_meta"):
            meta = self.store.get_vehicle_meta(vid) or {}

        dsn = str(meta.get("device_sn") or "").strip() or device_sn_of(
            self._veh_by_id.get(vid)
        )
        return vid, str(dsn or "").strip()

    def now_ms(self) -> str:
        """Corrected UTC milliseconds (local + server skew)."""
        return str(int(time.time() * 1000) + int(self._time_skew_ms))

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
            "version": API_VERSION,
        }

        tok = token if token is not None else self.token
        if tok:
            h["token"] = tok

        return h

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        sign_params: dict[str, Any] | None = None,
        token: str | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        log_vehicle_id: str | None = None,
    ) -> dict[str, Any]:
        """Signed GET once; no auth retry.

        ``params`` become query string + sign payload. ``sign_params`` are
        signed only (path-id endpoints like isOnline).
        """
        query = {k: ("" if v is None else str(v)) for k, v in (params or {}).items()}
        sign = {**(sign_params or {}), **query}

        kwargs: dict[str, Any] = {
            "headers": self.headers_for(sign, token=token),
            "timeout": timeout or _HTTP_TIMEOUT,
        }
        if query:
            kwargs["params"] = query

        started = datetime.now(timezone.utc).isoformat()
        http_status: int | None = None
        body: dict[str, Any] | None = None
        error: str | None = None
        try:
            async with self.session.get(self.api_base + path, **kwargs) as r:
                http_status = getattr(r, "status", None)
                raw = await r.json()
            if isinstance(raw, dict):
                body = raw
            else:
                body = None
                error = "non_object_json"
        except Exception as err:
            error = type(err).__name__
            self._record_query(
                method="GET",
                path=path,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                http_status=http_status,
                body=None,
                error=error,
                log_vehicle_id=log_vehicle_id,
            )
            raise
        self._record_query(
            method="GET",
            path=path,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            http_status=http_status,
            body=body,
            error=error,
            log_vehicle_id=log_vehicle_id,
        )
        return body if isinstance(body, dict) else {}

    async def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        token: str | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        include_timestamp_in_body: bool = False,
        log_vehicle_id: str | None = None,
    ) -> dict[str, Any]:
        """Signed POST once; no auth retry.

        Signature always covers ``{**body, timestamp}``. When
        ``include_timestamp_in_body`` is True the JSON body also includes
        ``timestamp`` (login / remoteControl / deviceLocate).
        """
        ts = self.now_ms()
        sign_params = {**body, "timestamp": ts}
        payload = {**body, "timestamp": ts} if include_timestamp_in_body else body

        headers = {
            "timestamp": ts,
            "signature": self.sign(sign_params),
            "user-agent": USER_AGENT,
            "content-type": "application/json",
            "language": "en",
            "version": API_VERSION,
        }
        if token:
            headers["token"] = token

        started = datetime.now(timezone.utc).isoformat()
        http_status: int | None = None
        parsed: dict[str, Any] | None = None
        error: str | None = None
        try:
            async with self.session.post(
                self.api_base + path,
                data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                headers=headers,
                timeout=timeout or _HTTP_TIMEOUT,
            ) as r:
                http_status = getattr(r, "status", None)
                raw = await r.json()
            if isinstance(raw, dict):
                parsed = raw
            else:
                error = "non_object_json"
        except Exception as err:
            error = type(err).__name__
            self._record_query(
                method="POST",
                path=path,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                http_status=http_status,
                body=None,
                error=error,
                log_vehicle_id=log_vehicle_id,
            )
            raise
        self._record_query(
            method="POST",
            path=path,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            http_status=http_status,
            body=parsed,
            error=error,
            log_vehicle_id=log_vehicle_id,
        )
        return parsed if isinstance(parsed, dict) else {}

    async def sync_server_time(self) -> int | None:
        """GET /pub/timestamp — update clock skew; return server epoch ms or None."""
        started = datetime.now(timezone.utc).isoformat()
        http_status: int | None = None
        d: dict[str, Any] | None = None
        error: str | None = None
        try:
            async with self.session.get(
                self.api_base + "/pub/timestamp",
                headers={"user-agent": USER_AGENT, "language": "en"},
                timeout=_HTTP_TIMEOUT,
            ) as r:
                http_status = getattr(r, "status", None)
                raw = await r.json()
            d = raw if isinstance(raw, dict) else None
            if d is None:
                error = "non_object_json"
        except Exception as err:
            error = type(err).__name__
            _LOGGER.debug("pub/timestamp failed", exc_info=True)
            self._record_query(
                method="GET",
                path="/pub/timestamp",
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                http_status=http_status,
                body=None,
                error=error,
            )
            return None

        self._record_query(
            method="GET",
            path="/pub/timestamp",
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            http_status=http_status,
            body=d,
            error=error,
        )

        if not d or str(d.get("code") or "") not in (OK_CODE, "0"):
            _LOGGER.debug(f"pub/timestamp code={d.get('code')} msg={d.get('msg')}")
            return None

        raw = d.get("data")
        try:
            server_ms = int(raw)
        except (TypeError, ValueError):
            _LOGGER.debug(f"pub/timestamp bad data={raw!r}")
            return None

        local_ms = int(time.time() * 1000)
        self._time_skew_ms = server_ms - local_ms
        _LOGGER.debug(f"server time skew_ms={self._time_skew_ms}")
        return server_ms

    async def _request_authed(
        self,
        call: Callable[[str], Awaitable[dict[str, Any]]],
        *,
        path: str,
        retry_any_error: bool = False,
        raise_if_still_stale: bool = False,
    ) -> dict[str, Any]:
        """Ensure token, invoke ``call(token)``, re-login once on failure."""
        tok = self.token or await self.login()
        d = await call(tok)
        code = str(d.get("code") or "")

        should_retry = code != OK_CODE if retry_any_error else code in STALE_TOKEN_CODES
        if should_retry:
            _LOGGER.debug(f"stale token on {path}; re-login and retry")
            d = await call(await self.login())

        if raise_if_still_stale and str(d.get("code") or "") in STALE_TOKEN_CODES:
            raise AuthError(f"stale token on {path}: {d}")

        return d if isinstance(d, dict) else {}

    async def _signed_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        log_vehicle_id: str | None = None,
    ) -> dict[str, Any]:
        """GET path with signed query params; re-login once on stale token."""
        self.reload_ids_from_store()

        _LOGGER.debug(f"GET {path}")

        return await self._request_authed(
            lambda tok: self._get(
                path, params=params, token=tok, log_vehicle_id=log_vehicle_id
            ),
            path=path,
            raise_if_still_stale=True,
        )

    async def _signed_post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: aiohttp.ClientTimeout | None = None,
        include_timestamp_in_body: bool = False,
        log_vehicle_id: str | None = None,
    ) -> dict[str, Any]:
        """POST path with signed body; re-login once on stale token."""
        _LOGGER.debug(f"POST {path}")

        return await self._request_authed(
            lambda tok: self._post(
                path,
                body,
                token=tok,
                timeout=timeout,
                include_timestamp_in_body=include_timestamp_in_body,
                log_vehicle_id=log_vehicle_id,
            ),
            path=path,
        )

    async def login(self):
        """Log in with credentials; persist token via CarlinkoStore."""
        if not self.email or not self.password:
            raise RuntimeError(
                "email / password missing — pass credentials to ApiClient "
                "(HA: config entry; engine: .env / CLI)"
            )

        ts = self.now_ms()
        body = {
            "account": self.email,
            "password": self.password,
            **LOGIN_BODY_DEFAULTS,
            "dateTime": ts,
            "timestamp": ts,
        }
        h = {
            "timestamp": ts,
            "signature": self.sign({**body, "timestamp": ts}),
            "user-agent": USER_AGENT,
            "content-type": "application/json",
            "language": "en",
            "version": API_VERSION,
        }

        async with self.session.post(
            self.api_base + "/user/login",
            data=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
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

        try:
            await self.sync_server_time()
        except Exception:
            _LOGGER.debug("server time sync after login failed", exc_info=True)

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

    async def async_list_vehicles(self, force: bool = False) -> list[dict[str, Any]]:
        """Fetch full /user/vehicle list and refresh per-vehicle caps (~1h TTL)."""
        if not force and self._veh_list and (time.time() - self._list_cache_t) < 3600:
            return list(self._veh_list)

        _LOGGER.debug("GET /user/vehicle")

        d = await self._request_authed(
            lambda tok: self._get("/user/vehicle", token=tok),
            path="/user/vehicle",
            retry_any_error=True,
        )

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
        """Fetch vehicles; return the row for ``vehicle_id`` (empty if omitted/unknown)."""
        await self.async_list_vehicles(force=force)

        if not vehicle_id:
            return {}

        return dict(self._veh_by_id.get(str(vehicle_id)) or {})

    def get_vehicle(self, vehicle_id: str) -> dict[str, Any]:
        vid = str(vehicle_id or "").strip()
        if not vid:
            return {}

        return dict(self._veh_by_id.get(vid) or {})

    def control_caps(self, vehicle_id: str) -> dict[str, Any]:
        """Capabilities from cached vehicle data (no network)."""
        vid = str(vehicle_id or "").strip()
        if vid and vid in self._caps_by_id:
            return dict(self._caps_by_id[vid])

        return {}

    async def send_control(
        self,
        opcode,
        timeout=20,
        *,
        vehicle_id: str,
        device_sn: str | None = None,
    ):
        """POST /user/vehicle/remoteControl for one vehicle."""
        self.reload_ids_from_store()

        vid, resolved_sn = self.ids_for(vehicle_id)
        dsn = str(device_sn or "").strip() or resolved_sn

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

        d = await self._signed_post(
            "/user/vehicle/remoteControl",
            body,
            timeout=post_timeout,
            include_timestamp_in_body=True,
        )

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

    async def device_locate(
        self,
        *,
        vehicle_id: str | None = None,
        device_sn: str | None = None,
    ) -> dict[str, Any]:
        """POST /maps/deviceLocate — vehicle GPS + optional reverse-geocoded address."""
        self.reload_ids_from_store()

        sn = str(device_sn or "").strip()
        if not sn and vehicle_id:
            _, sn = self.ids_for(vehicle_id)
        if not sn:
            _LOGGER.warning("deviceLocate skipped device_sn missing")
            return {"code": "-1", "msg": "device_sn missing"}

        d = await self._signed_post(
            "/maps/deviceLocate",
            {"sn": sn, "showAddress": 1},
            include_timestamp_in_body=True,
            log_vehicle_id=str(vehicle_id or "").strip() or self._vehicle_id_for_sn(sn),
        )

        code = str(d.get("code") or "")

        if code in (OK_CODE, "0"):
            _LOGGER.info(f"deviceLocate ok code={d.get('code')}")
        elif code in LOCATION_UNSUPPORTED_CODES:
            _LOGGER.info(
                f"deviceLocate unsupported code={d.get('code')} msg={d.get('msg')}"
            )
        elif code:
            # e.g. 50052 query failed — expected when offline / no GPS fix
            _LOGGER.debug(f"deviceLocate code={d.get('code')} msg={d.get('msg')}")

        return d

    async def is_online(self, vehicle_id: str) -> bool | None:
        """GET /user/vehicle/isOnline/{vehicleId}; None on error / bad payload."""
        self.reload_ids_from_store()

        vid = str(vehicle_id or "").strip()
        if not vid:
            return None

        path = f"/user/vehicle/isOnline/{vid}"

        _LOGGER.debug("GET /user/vehicle/isOnline")

        d = await self._request_authed(
            lambda tok: self._get(
                path,
                sign_params={"id": vid},
                token=tok,
                log_vehicle_id=vid,
            ),
            path="/user/vehicle/isOnline",
        )

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"isOnline failed vehicle={partial_id(vid)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return None

        data = d.get("data")

        if isinstance(data, bool):
            return data

        if data in (0, 1, "0", "1", "true", "false", "True", "False"):
            return str(data).lower() in ("1", "true")

        return None

    async def get_vehicle_state(self, vehicle_id: str) -> dict[str, Any]:
        """GET /user/vehicle/state/{vehicleId} — same telemetry hex as WS action:6."""
        self.reload_ids_from_store()

        vid = str(vehicle_id or "").strip()
        if not vid:
            return {"code": "-1", "msg": "vehicle_id missing"}

        path = f"/user/vehicle/state/{vid}"
        _LOGGER.debug("GET /user/vehicle/state")

        return await self._request_authed(
            lambda tok: self._get(
                path,
                sign_params={"id": vid},
                token=tok,
                log_vehicle_id=vid,
            ),
            path="/user/vehicle/state",
        )

    async def get_ws_connect(self, device_sn: str) -> str | None:
        """GET /netty/getConnect/2/{deviceSn} — WS base URL, or None on failure."""
        sn = str(device_sn or "").strip()
        if not sn:
            return None

        path = f"/netty/getConnect/2/{sn}"
        _LOGGER.debug("GET /netty/getConnect")

        d = await self._request_authed(
            lambda tok: self._get(
                path,
                sign_params={"sn": sn},
                token=tok,
                log_vehicle_id=self._vehicle_id_for_sn(sn),
            ),
            path="/netty/getConnect",
        )

        if str(d.get("code") or "") not in (OK_CODE, "0"):
            _LOGGER.debug(
                f"getConnect failed device={partial_id(sn)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return None

        data = d.get("data")
        url = ""
        if isinstance(data, str):
            url = data.strip()
        elif isinstance(data, dict):
            url = str(
                data.get("url") or data.get("wsUrl") or data.get("ws") or ""
            ).strip()

        # Live API returns http(s)://…:4002; app/WS client use ws(s)://.
        if url.startswith("http://"):
            url = "ws://" + url[len("http://") :]
        elif url.startswith("https://"):
            url = "wss://" + url[len("https://") :]

        if not url.startswith("ws"):
            return None

        if not url.endswith("/"):
            url += "/"

        return url

    @staticmethod
    def _page_payload(d: dict[str, Any]) -> dict[str, Any]:
        """Normalize list+total envelope; empty on non-OK."""
        if str(d.get("code")) != OK_CODE:
            return {"total": 0, "data": []}

        raw = d.get("data")

        if isinstance(raw, list):
            items = [r for r in raw if isinstance(r, dict)]
        elif isinstance(raw, dict):
            items = [raw]
        else:
            items = []

        try:
            total = int(d.get("total") if d.get("total") is not None else len(items))
        except (TypeError, ValueError):
            total = len(items)

        return {"total": total, "data": items}

    async def get_notice_unread_count(
        self, vehicle_id: str | None = None
    ) -> dict[str, Any]:
        """GET /user/notice/unReadCount — optional vehicleId (global when omitted)."""
        vid = str(vehicle_id or "").strip()
        params = {"vehicleId": vid} if vid else None

        d = await self._signed_get(
            "/user/notice/unReadCount", params, log_vehicle_id=vid or None
        )

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"unReadCount failed vehicle={partial_id(vid) if vid else 'global'} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return {}

        data = d.get("data")

        return dict(data) if isinstance(data, dict) else {}

    async def get_notices(
        self,
        vehicle_id: str | None,
        notice_type: int,
        *,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """GET /user/notice/page — optional vehicleId (global when omitted)."""
        vid = str(vehicle_id or "").strip()
        params: dict[str, Any] = {
            "page": page,
            "size": size,
            "type": notice_type,
        }
        if vid:
            params["vehicleId"] = vid

        d = await self._signed_get(
            "/user/notice/page", params, log_vehicle_id=vid or None
        )

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"notice page failed vehicle={partial_id(vid) if vid else 'global'} "
                f"type={notice_type} code={d.get('code')} msg={d.get('msg')}"
            )

        return self._page_payload(d)

    async def get_maintain_page(
        self,
        vehicle_id: str,
        *,
        query_key: str = "",
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """GET /user/maintain/page — dealer service history."""
        vid = str(vehicle_id or "").strip()
        if not vid:
            return {"total": 0, "data": []}

        d = await self._signed_get(
            "/user/maintain/page",
            {
                "vehicleId": vid,
                "queryKey": query_key,
                "page": page,
                "size": size,
            },
            log_vehicle_id=vid,
        )

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"maintain page failed vehicle={partial_id(vid)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )

        return self._page_payload(d)

    async def get_maintain_details(self, maintain_id: str) -> dict[str, Any]:
        """GET /user/maintain/details/{maintainId}."""
        mid = str(maintain_id or "").strip()
        if not mid:
            return {}

        d = await self._signed_get(f"/user/maintain/details/{mid}", {"maintainId": mid})

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"maintain details failed id={partial_id(mid)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return {}

        data = d.get("data")

        return dict(data) if isinstance(data, dict) else {}

    async def get_higher_firmware(
        self, device_id: str, version: str
    ) -> dict[str, Any] | None:
        """GET /user/higherFirmware — None when no upgrade / soft failure."""
        did = str(device_id or "").strip()
        ver = str(version or "").strip()

        if not did or not ver:
            return None

        d = await self._signed_get(
            "/user/higherFirmware",
            {"deviceId": did, "version": ver},
            log_vehicle_id=self._vehicle_id_for_sn(did),
        )

        if str(d.get("code")) != OK_CODE:
            _LOGGER.debug(
                f"higherFirmware failed device={partial_id(did)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return None

        data = d.get("data")

        if data is None or data == "":
            return None

        if isinstance(data, dict):
            return dict(data)

        return None
