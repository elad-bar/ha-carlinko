"""CarLinko data coordinator — hub multi-vehicle WebSocket push + caps refresh."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
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
    CONF_AVAILABILITY_SECONDS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_STREAM_BACKSTOP,
    DOMAIN,
    OK_CODE,
    STALE_TOKEN_CODES,
    STREAM_BACKSTOP,
)
from ..managers.api_client import ApiClient, device_sn_of, vehicle_id_of
from ..models.entity_specs import get_entity_specs
from ..models.exceptions import AuthError
from ..models.vehicle_state import VehicleState
from ..managers.ws_client import WsClient
from .store import CarlinkoStore

_LOGGER = logging.getLogger(__name__)

# Listener: (vehicle_id, added_keys, removed_keys). vehicle_id "" = fleet set change hint.
EntityListener = Callable[[str, set[str], set[str]], None]


@dataclass
class VehicleRuntime:
    """Per-vehicle live state + WS task."""

    vehicle_id: str
    device_sn: str
    meta: dict[str, Any]
    vehicle_state: VehicleState = field(default_factory=VehicleState)
    last_update_ts: float = 0.0
    connected: bool = False
    spec_keys: set[str] = field(default_factory=set)
    ws_task: asyncio.Task | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)


class CarlinkoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns ApiClient + per-vehicle WsClients; pushes snapshots into HA."""

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
        region = entry.options.get(CONF_REGION) or entry.data.get(CONF_REGION) or ""
        self.api = ApiClient(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            region,
            store,
            session,
        )
        self._stop = asyncio.Event()
        self._caps_task: asyncio.Task | None = None
        self._vehicles: dict[str, VehicleRuntime] = {}
        self._entity_listeners: list[EntityListener] = []
        self.data: dict[str, Any] = {"vehicles": {}}

    @property
    def vehicle_ids(self) -> list[str]:
        return list(self._vehicles.keys())

    @property
    def vehicle_id(self) -> str:
        """First / legacy vehicle id (diagnostics / single-car helpers)."""
        if self._vehicles:
            return next(iter(self._vehicles))
        return str(self.store.get_vehicle_id() or self.entry.entry_id)

    def vehicle_runtime(self, vehicle_id: str) -> VehicleRuntime | None:
        return self._vehicles.get(str(vehicle_id))

    def vehicle_data(self, vehicle_id: str) -> dict[str, Any]:
        vehicles = (self.data or {}).get("vehicles") or {}
        return dict(vehicles.get(str(vehicle_id)) or {})

    def caps_for(self, vehicle_id: str) -> dict:
        try:
            return self.api.control_caps(vehicle_id) or {}
        except Exception:
            return {}

    @property
    def caps(self) -> dict:
        return self.caps_for(self.vehicle_id)

    def _availability_seconds(self) -> int:
        raw = self.entry.options.get(CONF_AVAILABILITY_SECONDS)
        try:
            return int(raw) if raw is not None else AVAILABILITY_SECONDS
        except (TypeError, ValueError):
            return AVAILABILITY_SECONDS

    def _stream_backstop(self) -> int:
        raw = self.entry.options.get(CONF_STREAM_BACKSTOP)
        try:
            return int(raw) if raw is not None else STREAM_BACKSTOP
        except (TypeError, ValueError):
            return STREAM_BACKSTOP

    def is_available(self, vehicle_id: str | None = None) -> bool:
        if vehicle_id:
            rt = self._vehicles.get(str(vehicle_id))
            if rt is None or not rt.last_update_ts:
                return False
            return (time.time() - rt.last_update_ts) <= self._availability_seconds()
        # Any vehicle fresh → hub considered live for coarse checks.
        return any(self.is_available(vid) for vid in self._vehicles)

    @property
    def last_update_ts(self) -> float:
        if not self._vehicles:
            return 0.0
        return max((rt.last_update_ts for rt in self._vehicles.values()), default=0.0)

    @property
    def connected(self) -> bool:
        return any(rt.connected for rt in self._vehicles.values())

    def register_entity_listener(self, listener: EntityListener) -> Callable[[], None]:
        self._entity_listeners.append(listener)

        def _unsub() -> None:
            if listener in self._entity_listeners:
                self._entity_listeners.remove(listener)

        return _unsub

    def current_spec_keys(self, vehicle_id: str | None = None) -> set[str]:
        if vehicle_id is None:
            keys: set[str] = set()
            for vid in self._vehicles:
                keys |= self.current_spec_keys(vid)
            return keys
        state = self.vehicle_data(vehicle_id)
        if not state:
            rt = self._vehicles.get(str(vehicle_id))
            state = dict(rt.vehicle_state.data) if rt else {}
        return {
            s.key
            for s in get_entity_specs(state=state, caps=self.caps_for(vehicle_id))
        }

    def _meta_from_api_row(self, veh: dict[str, Any]) -> dict[str, Any]:
        vid = vehicle_id_of(veh)
        return {
            "vehicle_id": vid,
            "device_sn": device_sn_of(veh),
            "plate": veh.get("licenseNumber") or veh.get("plate") or "—",
            "model": veh.get("model") or veh.get("modelName") or veh.get("oldModel") or "EV",
            "vin": veh.get("vin") or veh.get("VIN") or "—",
        }

    def _publish_data(self) -> None:
        vehicles: dict[str, Any] = {}
        for vid, rt in self._vehicles.items():
            state = dict(rt.vehicle_state.data or {})
            state["vehicle"] = {
                "plate": rt.meta.get("plate") or "—",
                "model": rt.meta.get("model") or "EV",
                "vin": rt.meta.get("vin") or "—",
            }
            state["vehicle_id"] = vid
            vehicles[vid] = state
        self.async_set_updated_data({"vehicles": vehicles})

    def _notify_listeners(
        self, vehicle_id: str, added: set[str], removed: set[str]
    ) -> None:
        for listener in list(self._entity_listeners):
            try:
                listener(vehicle_id, added, removed)
            except Exception:
                _LOGGER.exception("entity listener failed")

    async def async_start(self) -> None:
        await self.store.async_load()
        try:
            await self.api.login()
            rows = await self.api.async_list_vehicles(force=True)
            if not rows:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cannot_connect",
                )
            self._sync_vehicles_from_rows(rows)
        except Exception as err:
            if _is_auth_error(err):
                await self._async_handle_auth_failure(err)
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise
        self._stop.clear()
        for vid in list(self._vehicles):
            self._start_ws(vid)
        self._publish_data()
        for vid, rt in self._vehicles.items():
            rt.spec_keys = self.current_spec_keys(vid)
        self._caps_task = self.hass.async_create_background_task(
            self._caps_refresh_loop(), name=f"{DOMAIN}_caps"
        )

    def _sync_vehicles_from_rows(self, rows: list[dict[str, Any]]) -> None:
        """Update store + runtime from API list; start/stop WS as needed."""
        metas: dict[str, dict[str, Any]] = {}
        for row in rows:
            vid = vehicle_id_of(row)
            if not vid:
                continue
            metas[vid] = self._meta_from_api_row(row)
        self.store.set_vehicles(metas)

        old_ids = set(self._vehicles)
        new_ids = set(metas)

        for vid in old_ids - new_ids:
            self._stop_ws(vid)
            removed_keys = set(self._vehicles[vid].spec_keys)
            del self._vehicles[vid]
            self._notify_listeners(vid, set(), removed_keys)
            self._async_remove_device(vid)

        for vid, meta in metas.items():
            if vid in self._vehicles:
                self._vehicles[vid].meta = meta
                self._vehicles[vid].device_sn = str(meta.get("device_sn") or "")
            else:
                rt = VehicleRuntime(
                    vehicle_id=vid,
                    device_sn=str(meta.get("device_sn") or ""),
                    meta=meta,
                )
                rt.vehicle_state.update_metadata(
                    {
                        **self.store.data,
                        "vehicle": {
                            "plate": meta.get("plate") or "—",
                            "model": meta.get("model") or "EV",
                            "vin": meta.get("vin") or "—",
                        },
                    }
                )
                self._vehicles[vid] = rt
                if not self._stop.is_set() and self._caps_task is not None:
                    # Already running: start WS and notify entity add for all specs.
                    self._start_ws(vid)
                    keys = self.current_spec_keys(vid)
                    rt.spec_keys = keys
                    self._notify_listeners(vid, keys, set())

        if old_ids != new_ids:
            # Fleet membership changed — platforms may rebuild wanted set.
            self._notify_listeners("", set(), set())

    def _async_remove_device(self, vehicle_id: str) -> None:
        """Drop HA device registry entry when a vehicle leaves the account."""
        from homeassistant.helpers import device_registry as dr

        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, vehicle_id)})
        if device is not None:
            registry.async_update_device(
                device.id, remove_config_entry_id=self.entry.entry_id
            )

    def _start_ws(self, vehicle_id: str) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None or rt.ws_task is not None:
            return
        rt.stop = asyncio.Event()

        def _on_frame(state: dict, vid: str = vehicle_id) -> None:
            self.hass.loop.call_soon_threadsafe(
                self._handle_frame, vid, dict(state or {})
            )

        ws = WsClient(
            rt.vehicle_state,
            self.api,
            on_frame=_on_frame,
            vehicle_id=rt.vehicle_id,
            device_sn=rt.device_sn,
            stream_backstop_s=self._stream_backstop(),
        )
        rt.ws_task = self.hass.async_create_background_task(
            self._ws_runner(vehicle_id, ws), name=f"{DOMAIN}_ws_{vehicle_id}"
        )

    def _stop_ws(self, vehicle_id: str) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None:
            return
        rt.stop.set()
        task = rt.ws_task
        rt.ws_task = None
        if task:
            task.cancel()

    async def _ws_runner(self, vehicle_id: str, ws: WsClient) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None:
            return
        try:
            rt.connected = True
            await ws.run(rt.stop)
        except asyncio.CancelledError:
            raise
        except AuthError as err:
            await self._async_handle_auth_failure(err)
            _LOGGER.error("WebSocket auth failed; reauthentication required")
        except Exception:
            _LOGGER.exception("WebSocket runner stopped unexpectedly for %s", vehicle_id)
        finally:
            if rt is self._vehicles.get(vehicle_id):
                rt.connected = False

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
                rows = await self.api.async_list_vehicles(force=True)
                self._sync_vehicles_from_rows(rows)
                self._publish_data()
                for vid, rt in self._vehicles.items():
                    self._maybe_notify_spec_changes(vid)
            except AuthError as err:
                await self._async_handle_auth_failure(err)
                _LOGGER.error("Caps refresh auth failed; reauthentication required")
                return
            except Exception:
                _LOGGER.exception("vehicle cache refresh failed")

    @callback
    def _handle_frame(self, vehicle_id: str, state: dict) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None:
            return
        rt.last_update_ts = float(state.get("updated_ts") or time.time())
        self._publish_data()
        self._maybe_notify_spec_changes(vehicle_id)

    def _maybe_notify_spec_changes(self, vehicle_id: str) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None:
            return
        new_keys = self.current_spec_keys(vehicle_id)
        if new_keys == rt.spec_keys:
            return
        added = new_keys - rt.spec_keys
        removed = rt.spec_keys - new_keys
        rt.spec_keys = new_keys
        self._notify_listeners(vehicle_id, added, removed)

    async def async_send_control(
        self,
        opcode: str,
        timeout: int = 20,
        *,
        vehicle_id: str | None = None,
    ) -> dict:
        vid = str(vehicle_id or self.vehicle_id)
        rt = self._vehicles.get(vid)
        dsn = rt.device_sn if rt else ""
        try:
            result = await self.api.send_control(
                opcode, timeout=timeout, vehicle_id=vid, device_sn=dsn or None
            )
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

    async def async_stop(self) -> None:
        self._stop.set()
        tasks: list[asyncio.Task] = []
        for vid in list(self._vehicles):
            rt = self._vehicles[vid]
            rt.stop.set()
            if rt.ws_task:
                rt.ws_task.cancel()
                tasks.append(rt.ws_task)
                rt.ws_task = None
        if self._caps_task:
            self._caps_task.cancel()
            tasks.append(self._caps_task)
            self._caps_task = None
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _async_handle_auth_failure(self, err: Exception) -> None:
        """Clear dead token and prompt HA reauthentication."""
        _LOGGER.debug("auth failure: %s", err)
        self.api.token = ""
        self.store.set_token("")
        self.entry.async_start_reauth(self.hass)

    async def _async_update_data(self) -> dict[str, Any]:
        return dict(self.data or {"vehicles": {}})


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
