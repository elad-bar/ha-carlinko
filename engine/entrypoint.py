"""CarLinko WS stream → live entity change logs (dev harness; no HA).

Requires .env (CARLINKO_EMAIL / PASSWORD / REGION) and data/config.json.
Protocol code lives in custom_components/carlinko/protocol/.

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

import aiohttp

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from protocol_path import ensure_protocol_package

ensure_protocol_package(REPO)

from dotenv import load_dotenv

load_dotenv(os.path.join(REPO, ".env"))

from protocol.api_client import ApiClient
from protocol.config_manager import ConfigManager
from protocol.consts import USER_AGENT
from protocol.vehicle_state import VehicleState
from protocol.ws_client import WsClient
from entity_publisher import EntityPublisher
from log_setup import configure_logging

_LOGGER = logging.getLogger(__name__)

_CAPS_REFRESH_INTERVAL_S = 3300


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


def _register_stop_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
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
    config = ConfigManager()
    vehicle_state = VehicleState()

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": USER_AGENT},
    ) as session:
        api = ApiClient(email, password, region, config, session)
        entities = EntityPublisher(config, api.control_caps)
        ws = WsClient(
            vehicle_state,
            api,
            on_frame=entities.publish,
        )

        _LOGGER.info("logging in to CarLinko…")
        await api.login()
        await api.refresh_vehicle_cache(force=True)
        vehicle_state.update_metadata(config.data)
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


def main():
    configure_logging()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
