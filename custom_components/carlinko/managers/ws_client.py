"""CarLinko WebSocket client for the HA bridge.

Holds one persistent socket, receives pushed action:6 frames, decodes them via
an injected VehicleState, and notifies an optional on_frame callback.
Auth / vehicle ids come from ApiClient.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

import aiohttp

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ..common.consts import HEARTBEAT, OK_CODE, RECONNECT_WAIT, STREAM_BACKSTOP, TOUCH, USER_AGENT
from ..models.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)

_WS_CONNECT_TIMEOUT = aiohttp.ClientTimeout(total=20)
_RECV_TIMEOUT = 2.0


class WsClient:
    """Persistent CarLinko WS stream → VehicleState → optional on_frame(state)."""

    def __init__(self, vehicle_state, api_client, on_frame=None):
        self.vehicle_state = vehicle_state
        self.api = api_client
        self.on_frame = on_frame
        self.stream_backstop_s = STREAM_BACKSTOP

    def reload_config(self):
        self.api.reload_ids_from_store()
        cfg = self.api.store.data
        self.stream_backstop_s = int(cfg.get("stream_backstop") or STREAM_BACKSTOP)
        self.vehicle_state.update_metadata(cfg)

    async def connect(self, attempts=3):
        last = None
        headers = {"User-Agent": USER_AGENT}
        for i in range(attempts):
            try:
                return await self.api.session.ws_connect(
                    self.api.ws_url,
                    headers=headers,
                    timeout=_WS_CONNECT_TIMEOUT,
                    heartbeat=None,
                )
            except Exception as e:
                last = e
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
        ws = await self.connect()
        try:
            await self.ws_send(ws, {
                "action": 1,
                "data": {"token": self.api.token, "vehicleId": self.api.vehicle_id},
            })
            login_raw = await self.ws_recv(ws)
            login = json.loads(login_raw) if login_raw else {}
            if login.get("code") != OK_CODE:
                _LOGGER.warning(
                    "token invalid (code=%s); self-logging in",
                    login.get("code"),
                )
                await self.api.login()
                try:
                    await self.api.refresh_vehicle_cache(force=True)
                except AuthError:
                    raise
                except Exception:
                    _LOGGER.exception("vehicle cache refresh after login failed")
                await self.ws_send(ws, {
                    "action": 1,
                    "data": {"token": self.api.token, "vehicleId": self.api.vehicle_id},
                })
                login_raw = await self.ws_recv(ws)
                login = json.loads(login_raw) if login_raw else {}
                if login.get("code") != OK_CODE:
                    raise AuthError(
                        f"websocket login failed after refresh (code={login.get('code')})"
                    )
            await self.ws_send(ws, {"action": 6})
            await self.ws_send(ws, {"action": 0, "data": {"sn": self.api.device_sn}})
            last_hb = last_req = last_touch = time.time()
            last_blob = None
            while not stop.is_set():
                now = time.time()
                if now - last_hb >= HEARTBEAT:
                    await self.ws_send(ws, {"action": 0, "data": {"sn": self.api.device_sn}})
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
                    continue
                if j.get("action") == 6 and isinstance(j.get("data"), str):
                    blob = j["data"]
                    changed = blob != last_blob
                    if changed or time.time() - last_touch >= TOUCH:
                        d = self._emit(blob)
                        last_touch = time.time()
                        _LOGGER.debug(
                            "%s  batt=%s%%  range=%skm  odo=%s  %s",
                            time.strftime("%H:%M:%S"),
                            d.get("battery"),
                            d.get("range"),
                            d.get("odo"),
                            "push" if changed else "touch",
                        )
                    last_blob = blob
        finally:
            await ws.close()

    async def run(self, stop: asyncio.Event):
        """Persistent-socket ingest until stop is set. Reconnects on drop."""
        self.reload_config()
        _LOGGER.info(
            "streaming CarLinko WS (push + %ss heartbeat, auto-reconnect)",
            HEARTBEAT,
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
