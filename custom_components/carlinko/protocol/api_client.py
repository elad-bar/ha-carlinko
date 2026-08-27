"""CarLinko HTTP API client: login, signing, vehicle fetch, remote control.

Signing recovered from libapp.so (Blutter): see docs/decompiled/secure_*_utils.dart.
  signature = base64(HMAC-SHA256(SIGN_KEY,
              jsonEncode(sortByKeyAsc({...params, timestamp}))))   # Dart jsonEncode = no spaces
Login = POST /user/login with a plaintext password body. The `v-data` header the app sends is
NOT validated by the server, so we omit it.

Secrets (email / password / region) come from the environment; token + vehicle ids from ConfigManager.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

import aiohttp

from .consts import (
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
from .exceptions import AuthError
from .helpers import flag, flags, parse_control_cfg, seat_max

_LOGGER = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)


class ApiClient:
    """Signed CarLinko REST calls over an injected aiohttp ClientSession."""

    def __init__(self, email, password, region, config, session: aiohttp.ClientSession):
        self.email = (email or "").strip()
        self.password = password or ""
        self.region = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
        self.config = config
        self.session = session
        sk = config.data.get("sign_key") or DEFAULT_SIGN_KEY
        self.sign_key = sk.encode() if isinstance(sk, str) else sk
        self.api_base = API_HOST_TMPL.format(region=self.region)
        self.ws_url = WS_HOST_TMPL.format(region=self.region)
        self.token = (config.data.get("token") or "").strip()
        self.vehicle_id = str(config.data.get("vehicle_id") or "")
        self.device_sn = str(config.data.get("device_sn") or "")
        self._veh_cache = {"t": 0.0, "v": None}
        self._caps_cache: dict = {}

    def reload_ids_from_config(self):
        self.config.load()
        self.token = (self.config.data.get("token") or "").strip() or self.token
        self.vehicle_id = str(self.config.data.get("vehicle_id") or "") or self.vehicle_id
        self.device_sn = str(self.config.data.get("device_sn") or "") or self.device_sn
        sk = self.config.data.get("sign_key") or DEFAULT_SIGN_KEY
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
        return base64.b64encode(hmac.new(self.sign_key, msg, hashlib.sha256).digest()).decode()

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
        """Log in with env credentials; persist token to config.json."""
        if not self.email or not self.password:
            raise RuntimeError(
                "CARLINKO_EMAIL / CARLINKO_PASSWORD missing — see .env.example / README"
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
        if str(d.get("code")) != OK_CODE:
            raise AuthError(f"login failed: {d}")
        data = d.get("data") or {}
        token = data.get("token") if isinstance(data, dict) else data
        if not token:
            raise AuthError(f"login ok but no token in response: {d}")
        self.token = token
        self.config.set_token(token)
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
        out["seats"] = {
            oid: seat_max(ac, fkey, lkey) for oid, fkey, lkey in SEAT_CAPS
        }
        out["plate"] = v.get("licenseNumber") or ""
        return out

    async def refresh_vehicle_cache(self, force=False):
        """Fetch /user/vehicle and refresh caps cache (~1h TTL unless force)."""
        if (
            not force
            and self._veh_cache["v"] is not None
            and (time.time() - self._veh_cache["t"]) < 3600
        ):
            return self._veh_cache["v"]

        async def _fetch(tok):
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
            d = await _fetch(await self.login())
        data = d.get("data")
        v = (data[0] if isinstance(data, list) and data else data) if data else {}
        self._veh_cache["v"] = v or {}
        self._veh_cache["t"] = time.time()
        try:
            self._caps_cache = self._caps_from_vehicle(self._veh_cache["v"])
        except Exception:
            self._caps_cache = {}
        return self._veh_cache["v"]

    def control_caps(self):
        """Capabilities from cached vehicle data (no network)."""
        return dict(self._caps_cache)

    async def send_control(self, opcode, timeout=20):
        """POST /user/vehicle/remoteControl."""
        self.reload_ids_from_config()
        vid = self.vehicle_id
        dsn = self.device_sn
        if not vid or not dsn:
            return {"code": "-1", "msg": "vehicle_id / device_sn missing from config.json"}
        try:
            timeout = int(timeout)
        except Exception:
            timeout = 20
        body = {"vehicleId": vid, "deviceSn": dsn, "data": str(opcode), "timeOut": timeout}
        post_timeout = aiohttp.ClientTimeout(total=timeout + 8)

        async def _post(tok):
            ts = self.now_ms()
            ordered = {k: v for k, v in sorted({**body, "timestamp": ts}.items())}
            msg = json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode()
            sig = base64.b64encode(hmac.new(self.sign_key, msg, hashlib.sha256).digest()).decode()
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
        d = await _post(tok)
        if str(d.get("code")) in STALE_TOKEN_CODES:
            d = await _post(await self.login())
        _LOGGER.info(
            "remoteControl opcode=%s code=%s",
            opcode,
            d.get("code"),
        )
        return d
