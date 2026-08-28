"""CarLinko WS stream → live entity change logs (dev harness; no HA).

Requires .env (CARLINKO_EMAIL / PASSWORD / REGION) and data/config.json
(same CarlinkoStore as HA, file-backed). HA-free code lives in
custom_components/carlinko/{managers,models}/.

Usage:
  python entrypoint.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from typing import Any, Callable

import aiohttp
from carlinko.common.consts import USER_AGENT
from carlinko.managers.api_client import ApiClient
from carlinko.managers.store import CarlinkoStore
from carlinko.managers.ws_client import WsClient
from carlinko.models.entity_specs import ENTITY_SPECS, get_entity_specs
from carlinko.models.entity_values import EntityValueResolver
from carlinko.models.vehicle_state import VehicleState
from dotenv import load_dotenv
import ha_free_path  # noqa: F401  # mounts synthetic carlinko package

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

load_dotenv(os.path.join(REPO, ".env"))

_CAPS_REFRESH_INTERVAL_S = 3300
_LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    raw = (os.environ.get("CARLINKO_LOG_LEVEL") or "").strip().upper()
    if raw:
        level = getattr(logging, raw, logging.INFO)
    else:
        debug = str(os.environ.get("DEBUG", "")).lower() == "true"
        level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(threadName)s[%(thread)d] %(levelname)s %(name)s %(message)s"
        )
    )
    root.addHandler(handler)
    for name in ("aiohttp", "aiohttp.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


class EntityPublisher:
    """Dev-only: resolve EntitySpecs → INFO logs on value change."""

    def __init__(self, store: CarlinkoStore, get_caps: Callable[[], dict]):
        self.store = store
        self.get_caps = get_caps
        self._resolver = EntityValueResolver(store)
        self._last: dict[str, Any] = {}

    def publish(self, state: dict) -> None:
        try:
            caps = self.get_caps() or {}
        except Exception:
            caps = {}
        state = state or {}
        specs = get_entity_specs(state=state, caps=caps)
        active = set()
        for spec in specs:
            active.add(spec.key)
            if not spec.has_live_state():
                continue
            value = self._resolver.resolve_value(spec, state)
            if spec.key not in self._last or self._last[spec.key] != value:
                old = (
                    "—"
                    if spec.key not in self._last
                    else spec.format_value(self._last[spec.key])
                )
                _LOGGER.info(
                    "%s: %s → %s",
                    spec.name,
                    old,
                    spec.format_value(value),
                )
                self._last[spec.key] = value
        for key in list(self._last):
            if key not in active:
                del self._last[key]

    def log_command(self, key: str, action: str | None = None) -> None:
        spec = next((s for s in ENTITY_SPECS if s.key == key), None)
        if not spec:
            _LOGGER.info("command %s %s", key, action)
            return
        if action is None and spec.platform == "button":
            action = "press"
        _LOGGER.info("%s", spec.format_command(action))


def _env_secrets():
    email = (os.environ.get("CARLINKO_EMAIL") or "").strip()
    password = os.environ.get("CARLINKO_PASSWORD") or ""
    region = (os.environ.get("CARLINKO_REGION") or "").strip()
    if not email or not password:
        _LOGGER.error(
            "CARLINKO_EMAIL / CARLINKO_PASSWORD missing — copy .env.example → .env"
        )
        sys.exit(2)
    return email, password, region


async def _caps_refresh_loop(api: ApiClient, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_CAPS_REFRESH_INTERVAL_S)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await api.refresh_vehicle_cache(force=True)
        except Exception:
            _LOGGER.exception("vehicle cache refresh failed")


def _register_stop_handlers(
    loop: asyncio.AbstractEventLoop, stop: asyncio.Event
) -> None:
    def request_stop(*_):
        _LOGGER.info("shutting down")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


async def async_main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    _register_stop_handlers(loop, stop)

    email, password, region = _env_secrets()
    store = CarlinkoStore.for_engine()
    vehicle_state = VehicleState()

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": USER_AGENT},
    ) as session:
        api = ApiClient(email, password, region, store, session)
        entities = EntityPublisher(store, api.control_caps)
        ws = WsClient(
            vehicle_state,
            api,
            on_frame=entities.publish,
        )

        _LOGGER.info("logging in to CarLinko…")
        await api.login()
        await api.refresh_vehicle_cache(force=True)
        vehicle_state.update_metadata(store.data)
        _LOGGER.info("streaming CarLinko WS → entity change logs…")

        refresh_task = asyncio.create_task(_caps_refresh_loop(api, stop))
        try:
            await ws.run(stop)
        finally:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass


def main() -> None:
    _configure_logging()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
