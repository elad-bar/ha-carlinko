"""CarLinko WebSocket client (HA-free at module load).

Holds one persistent socket, receives pushed action:6 frames, decodes them via
an injected VehicleState, and notifies optional on_frame / on_connected callbacks.
Auth / vehicle ids come from ApiClient + explicit vehicle_id / device_sn.

Must not import homeassistant. Engine CLI owns stdout encoding setup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging
import time
from typing import Any

import aiohttp

from ..common.consts import (
    HEARTBEAT,
    OK_CODE,
    RECONNECT_WAIT,
    STREAM_BACKSTOP,
    TOUCH,
    USER_AGENT,
)
from ..models.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)

_WS_CONNECT_TIMEOUT = aiohttp.ClientWSTimeout(ws_close=20)
_RECV_TIMEOUT = 2.0


class WsClient:
    """Persistent CarLinko WS stream → VehicleState → optional callbacks."""

    def __init__(
        self,
        vehicle_state,
        api_client,
        on_frame: Callable[[dict[str, Any]], None] | None = None,
        *,
        on_connected: Callable[[bool], None] | None = None,
        vehicle_id: str | None = None,
        device_sn: str | None = None,
        stream_backstop_s: int | None = None,
    ):
        self.vehicle_state = vehicle_state
        self.api = api_client
        self.on_frame = on_frame
        self.on_connected = on_connected
        self.vehicle_id = str(vehicle_id or "")
        self.device_sn = str(device_sn or "")
        self.stream_backstop_s = int(
            stream_backstop_s if stream_backstop_s is not None else STREAM_BACKSTOP
        )

    def _set_connected(self, connected: bool) -> None:
        if self.on_connected:
            try:
                self.on_connected(connected)
            except Exception:
                _LOGGER.exception("on_connected error")

    def reload_config(self):
        self.api.reload_ids_from_store()
        cfg = self.api.store.data
        if not self.vehicle_id:
            self.vehicle_id = str(self.api.vehicle_id or "")
        if not self.device_sn:
            self.device_sn = str(self.api.device_sn or "")
        meta = {}
        if hasattr(self.api.store, "get_vehicle_meta") and self.vehicle_id:
            meta = self.api.store.get_vehicle_meta(self.vehicle_id)
            if meta.get("device_sn"):
                self.device_sn = str(meta["device_sn"])
        backstop = cfg.get("stream_backstop")
        if backstop is not None:
            self.stream_backstop_s = int(backstop)
        # Metadata for this vehicle (hub store or legacy).
        if meta:
            self.vehicle_state.update_metadata(
                {
                    **cfg,
                    "vehicle": {
                        "plate": meta.get("plate") or "—",
                        "model": meta.get("model") or "EV",
                        "vin": meta.get("vin") or "—",
                    },
                    "vehicle_id": self.vehicle_id,
                    "device_sn": self.device_sn,
                }
            )
        else:
            self.vehicle_state.update_metadata(cfg)

    async def connect(self, attempts=3):
        last = None
        headers = {"User-Agent": USER_AGENT}
        for i in range(attempts):
            try:
                ws = await self.api.session.ws_connect(
                    self.api.ws_url,
                    headers=headers,
                    timeout=_WS_CONNECT_TIMEOUT,
                    heartbeat=None,
                )
                _LOGGER.debug(f"websocket connect attempt {i + 1}/{attempts} ok")
                return ws
            except Exception as e:
                last = e
                _LOGGER.debug(
                    f"websocket connect attempt {i + 1}/{attempts} failed: {e}"
                )
                await asyncio.sleep(2 + i * 2)
        raise last

    @staticmethod
    async def ws_send(ws, obj):
        await ws.send_str(json.dumps(obj))

    @staticmethod
    async def ws_recv(ws):
        msg = await asyncio.wait_for(ws.receive(), timeout=_RECV_TIMEOUT)
        if msg.type == aiohttp.WSMsgType.TEXT:
            return msg.data
        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise ConnectionError(f"websocket closed: {msg.type}")
        return None

    def _emit(self, blob):
        """Blob hex → live state → on_frame callback."""
        state = self.vehicle_state.update_data(blob)
        if self.on_frame:
            try:
                self.on_frame(state)
            except Exception:
                _LOGGER.exception("on_frame error")
        return state

    async def _stream_session(self, stop: asyncio.Event):
        self.reload_config()
        vid = self.vehicle_id or self.api.vehicle_id
        dsn = self.device_sn or self.api.device_sn
        ws = await self.connect()
        try:
            await self.ws_send(
                ws,
                {
                    "action": 1,
                    "data": {"token": self.api.token, "vehicleId": vid},
                },
            )
            login_raw = await self.ws_recv(ws)
            login = json.loads(login_raw) if login_raw else {}
            if login.get("code") != OK_CODE:
                _LOGGER.warning(
                    f"token invalid (code={login.get('code')}); self-logging in"
                )
                await self.api.login()
                try:
                    await self.api.refresh_vehicle_cache(force=True, vehicle_id=vid)
                except AuthError:
                    raise
                except Exception:
                    _LOGGER.exception("vehicle cache refresh after login failed")
                await self.ws_send(
                    ws,
                    {
                        "action": 1,
                        "data": {"token": self.api.token, "vehicleId": vid},
                    },
                )
                login_raw = await self.ws_recv(ws)
                login = json.loads(login_raw) if login_raw else {}
                if login.get("code") != OK_CODE:
                    raise AuthError(
                        f"websocket login failed after refresh (code={login.get('code')})"
                    )
                _LOGGER.info("websocket login ok after token refresh")
            await self.ws_send(ws, {"action": 6})
            await self.ws_send(ws, {"action": 0, "data": {"sn": dsn}})
            self._set_connected(True)
            last_hb = last_req = last_touch = time.time()
            last_blob = None
            while not stop.is_set():
                now = time.time()
                if now - last_hb >= HEARTBEAT:
                    await self.ws_send(ws, {"action": 0, "data": {"sn": dsn}})
                    last_hb = now
                if now - last_req >= self.stream_backstop_s:
                    await self.ws_send(ws, {"action": 6})
                    last_req = now
                try:
                    msg = await self.ws_recv(ws)
                except asyncio.TimeoutError:
                    if last_blob and time.time() - last_touch >= TOUCH:
                        self._emit(last_blob)
                        last_touch = time.time()
                    continue
                if not msg:
                    continue
                try:
                    j = json.loads(msg)
                except Exception:
                    preview = msg[:120] if isinstance(msg, str) else repr(msg)[:120]
                    _LOGGER.warning(f"websocket non-JSON message: {preview}")
                    continue
                if j.get("action") == 6 and isinstance(j.get("data"), str):
                    blob = j["data"]
                    changed = blob != last_blob
                    if changed or time.time() - last_touch >= TOUCH:
                        d = self._emit(blob)
                        last_touch = time.time()
                        _LOGGER.debug(
                            f"{time.strftime('%H:%M:%S')}  veh={vid}  "
                            f"batt={d.get('battery')}%  range={d.get('range')}km  "
                            f"odo={d.get('odo')}  "
                            f"{'push' if changed else 'touch'}"
                        )
                    last_blob = blob
        finally:
            self._set_connected(False)
            await ws.close()

    async def run(self, stop: asyncio.Event):
        """Persistent-socket ingest until stop is set. Reconnects on drop."""
        self.reload_config()
        _LOGGER.info(
            f"streaming CarLinko WS vehicle={self.vehicle_id or self.api.vehicle_id} "
            f"(push + {HEARTBEAT}s heartbeat, auto-reconnect)"
        )
        while not stop.is_set():
            try:
                await self._stream_session(stop)
            except asyncio.CancelledError:
                raise
            except AuthError:
                raise
            except Exception:
                _LOGGER.warning("stream error, reconnecting", exc_info=True)
            if stop.is_set():
                break
            await asyncio.sleep(RECONNECT_WAIT)
