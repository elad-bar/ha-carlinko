"""CarLinko data coordinator — WebSocket push + caps refresh."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..common.consts import (
    AVAILABILITY_SECONDS,
    CAPS_REFRESH_INTERVAL_S,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
    OK_CODE,
    STALE_TOKEN_CODES,
)
from ..managers.api_client import ApiClient
from ..models.entity_specs import get_entity_specs
from ..models.exceptions import AuthError
from ..models.vehicle_state import VehicleState
from ..managers.ws_client import WsClient
from .store import CarlinkoStore

_LOGGER = logging.getLogger(__name__)


class CarlinkoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns ApiClient + WsClient; pushes VehicleState snapshots into HA."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: CarlinkoStore,
        session: ClientSession,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.entry = entry
        self.store = store
        self.api = ApiClient(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_REGION) or "",
            store,
            session,
        )
        self.vehicle_state = VehicleState()
        self._ws = WsClient(self.vehicle_state, self.api, on_frame=self._on_frame)
        self._stop = asyncio.Event()
        self._ws_task: asyncio.Task | None = None
        self._caps_task: asyncio.Task | None = None
        self._spec_keys: set[str] = set()
        self._entity_listeners: list[Callable[[set[str], set[str]], None]] = []
        self.last_update_ts: float = 0.0
        self.connected = False

    @property
    def vehicle_id(self) -> str:
        return str(
            self.api.vehicle_id or self.store.get_vehicle_id() or self.entry.entry_id
        )

    @property
    def caps(self) -> dict:
        try:
            return self.api.control_caps() or {}
        except Exception:
            return {}

    def is_available(self) -> bool:
        if not self.last_update_ts:
            return False
        return (time.time() - self.last_update_ts) <= AVAILABILITY_SECONDS

    def register_entity_listener(
        self, listener: Callable[[set[str], set[str]], None]
    ) -> Callable[[], None]:
        self._entity_listeners.append(listener)

        def _unsub() -> None:
            if listener in self._entity_listeners:
                self._entity_listeners.remove(listener)

        return _unsub

    def current_spec_keys(self) -> set[str]:
        state = self.data or self.vehicle_state.data or {}
        return {s.key for s in get_entity_specs(state=state, caps=self.caps)}

    async def async_start(self) -> None:
        await self.store.async_load()
        try:
            await self.api.login()
            veh = await self.api.refresh_vehicle_cache(force=True)
            self._sync_vehicle_into_store(veh or {})
        except Exception as err:
            if _is_auth_error(err):
                await self._async_handle_auth_failure(err)
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise
        self.vehicle_state.update_metadata(self.store.data)
        self._spec_keys = self.current_spec_keys()
        self.async_set_updated_data(dict(self.vehicle_state.data))
        self._stop.clear()
        self._ws_task = self.hass.async_create_background_task(
            self._ws_runner(), name=f"{DOMAIN}_ws"
        )
        self._caps_task = self.hass.async_create_background_task(
            self._caps_refresh_loop(), name=f"{DOMAIN}_caps"
        )

    def _sync_vehicle_into_store(self, veh: dict) -> None:
        """Persist vehicle_id / device_sn / plate / model / vin from /user/vehicle."""
        updates: dict[str, Any] = {}
        vid = veh.get("vehicleId") or veh.get("id")
        dsn = veh.get("deviceSn") or veh.get("deviceSN")
        if vid:
            updates["vehicle_id"] = str(vid)
            self.api.vehicle_id = str(vid)
        if dsn:
            updates["device_sn"] = str(dsn)
            self.api.device_sn = str(dsn)
        vehicle = dict(self.store.data.get("vehicle") or {})
        plate = veh.get("licenseNumber") or veh.get("plate")
        model = veh.get("model") or veh.get("modelName") or veh.get("oldModel")
        vin = veh.get("vin") or veh.get("VIN")
        if plate:
            vehicle["plate"] = plate
        if model:
            vehicle["model"] = model
        if vin:
            vehicle["vin"] = vin
        if vehicle:
            updates["vehicle"] = vehicle
        if updates:
            self.store.update(**updates)
            self.api.reload_ids_from_config()

    async def async_stop(self) -> None:
        self._stop.set()
        for task in (self._ws_task, self._caps_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._ws_task = None
        self._caps_task = None
        self.connected = False

    async def _ws_runner(self) -> None:
        try:
            self.connected = True
            await self._ws.run(self._stop)
        except asyncio.CancelledError:
            raise
        except AuthError as err:
            await self._async_handle_auth_failure(err)
            _LOGGER.error("WebSocket auth failed; reauthentication required")
        except Exception:
            _LOGGER.exception("WebSocket runner stopped unexpectedly")
        finally:
            self.connected = False

    async def _caps_refresh_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=CAPS_REFRESH_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                veh = await self.api.refresh_vehicle_cache(force=True)
                self._sync_vehicle_into_store(veh or {})
                self._maybe_notify_spec_changes()
            except AuthError as err:
                await self._async_handle_auth_failure(err)
                _LOGGER.error("Caps refresh auth failed; reauthentication required")
                return
            except Exception:
                _LOGGER.exception("vehicle cache refresh failed")

    def _on_frame(self, state: dict) -> None:
        self.hass.loop.call_soon_threadsafe(self._handle_frame, dict(state or {}))

    @callback
    def _handle_frame(self, state: dict) -> None:
        self.last_update_ts = float(state.get("updated_ts") or time.time())
        self.async_set_updated_data(state)
        self._maybe_notify_spec_changes()

    def _maybe_notify_spec_changes(self) -> None:
        new_keys = self.current_spec_keys()
        if new_keys == self._spec_keys:
            return
        added = new_keys - self._spec_keys
        removed = self._spec_keys - new_keys
        self._spec_keys = new_keys
        for listener in list(self._entity_listeners):
            try:
                listener(added, removed)
            except Exception:
                _LOGGER.exception("entity listener failed")

    async def async_send_control(self, opcode: str, timeout: int = 20) -> dict:
        try:
            result = await self.api.send_control(opcode, timeout=timeout)
        except Exception as err:
            if _is_auth_error(err):
                await self._async_handle_auth_failure(err)
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        code = str(result.get("code") or "")
        if code in STALE_TOKEN_CODES:
            await self._async_handle_auth_failure(
                AuthError(f"token stale (code={code})")
            )
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            )
        if code and code not in (OK_CODE, "0"):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={
                    "error": f"code={code} msg={result.get('msg')}"
                },
            )
        return result

    async def _async_handle_auth_failure(self, err: Exception) -> None:
        """Clear dead token and prompt HA reauthentication."""
        _LOGGER.debug("auth failure: %s", err)
        self.api.token = ""
        self.store.set_token("")
        self.entry.async_start_reauth(self.hass)

    async def _async_update_data(self) -> dict[str, Any]:
        return dict(self.vehicle_state.data)


def _is_auth_error(err: Exception) -> bool:
    if isinstance(err, AuthError):
        return True
    text = str(err).lower()
    return any(x in text for x in ("login failed", "9997", "401", "invalid_auth"))


async def async_create_coordinator(
    hass: HomeAssistant, entry: ConfigEntry
) -> CarlinkoCoordinator:
    store = CarlinkoStore(hass, entry.entry_id)
    session = async_get_clientsession(hass)
    return CarlinkoCoordinator(hass, entry, store, session)
