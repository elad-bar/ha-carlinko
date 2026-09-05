"""CarLinko data coordinator — hub multi-vehicle WebSocket push + caps refresh."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import time
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..common.consts import (
    AVAILABILITY_SECONDS,
    CAPS_REFRESH_INTERVAL_S,
    CONF_AVAILABILITY_SECONDS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_STREAM_BACKSTOP,
    DOMAIN,
    EVENT_NOTICE,
    FIRMWARE_POLL_INTERVAL_S,
    FIRMWARE_VERSION_FALLBACK,
    LOCATION_POLL_INTERVAL_S,
    MAINTAIN_POLL_INTERVAL_S,
    NOTICE_OPERATIONAL_TYPES,
    NOTICE_POLL_INTERVAL_S,
    NOTICE_TYPE_NAMES,
    OK_CODE,
    REST_STATE_POLL_INTERVAL_S,
    STALE_TOKEN_CODES,
    STORAGE_VERSION,
    STREAM_BACKSTOP,
    USER_AGENT,
    WS_SETUP_TIMEOUT_S,
)
from ..common.helpers import (
    interpret_device_locate_code,
    partial_id,
    require_region_from_entry_data,
)
from ..managers.api_client import ApiClient, meta_from_api_row, vehicle_id_of
from ..managers.ws_client import WsClient
from ..models.entity_specs import get_entity_specs
from ..models.exceptions import AuthError
from ..models.vehicle_images import IMAGE_ANGLES
from ..models.vehicle_state import VehicleState
from .store import CarlinkoStore, ha_storage_key

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
        try:
            region = require_region_from_entry_data(entry.data)
        except ValueError as err:
            _LOGGER.error(f"setup failed entry_id={partial_id(entry.entry_id)} {err}")
            raise ConfigEntryError(
                f"CarLinko config entry is missing or has invalid region: {err}"
            ) from err
        self.api = ApiClient(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            region,
            store,
            session,
        )
        self._stop = asyncio.Event()
        self._caps_task: asyncio.Task | None = None
        self._location_task: asyncio.Task | None = None
        self._notice_task: asyncio.Task | None = None
        self._maintain_task: asyncio.Task | None = None
        self._firmware_task: asyncio.Task | None = None
        self._rest_state_task: asyncio.Task | None = None
        self._vehicles: dict[str, VehicleRuntime] = {}
        self._entity_listeners: list[EntityListener] = []
        self._was_available: dict[str, bool] = {}
        self.data: dict[str, Any] = {"vehicles": {}}
        # Last operational unread sum per vehicle (drives notice page fetch).
        self._notice_unread_seen: dict[str, int] = {}

    @property
    def vehicle_ids(self) -> list[str]:
        return list(self._vehicles.keys())

    @property
    def vehicle_id(self) -> str:
        """First vehicle id for diagnostics only. Prefer vehicle_ids / explicit id."""
        if self._vehicles:
            return next(iter(self._vehicles))
        return str(self.store.get_vehicle_id() or "")

    def vehicle_runtime(self, vehicle_id: str) -> VehicleRuntime | None:
        return self._vehicles.get(str(vehicle_id))

    def vehicle_data(self, vehicle_id: str) -> dict[str, Any]:
        vehicles = (self.data or {}).get("vehicles") or {}
        return dict(vehicles.get(str(vehicle_id)) or {})

    def caps_for(self, vehicle_id: str) -> dict:
        try:
            caps = dict(self.api.control_caps(vehicle_id) or {})
        except Exception:
            caps = {}
        meta = self.store.get_vehicle_meta(vehicle_id)
        if meta.get("location_supported") is True:
            caps["location"] = True
        return caps

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
            if rt is None or not rt.connected or not rt.last_update_ts:
                return False
            return (time.time() - rt.last_update_ts) <= self._availability_seconds()
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
            s.key for s in get_entity_specs(state=state, caps=self.caps_for(vehicle_id))
        }

    def _apply_location_to_runtime(
        self,
        vehicle_id: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        address: str | None = None,
    ) -> None:
        """Write location into VehicleState + refresh meta from store."""
        rt = self._vehicles.get(str(vehicle_id))
        if rt is None:
            return
        rt.meta = self.store.get_vehicle_meta(vehicle_id)
        loc = dict(rt.vehicle_state.data.get("location") or {})
        if lat is not None:
            loc["lat"] = lat
        if lng is not None:
            loc["lng"] = lng
        if address is not None:
            loc["address"] = address
        # Seed from persisted meta when runtime has no coords yet.
        if loc.get("lat") is None and rt.meta.get("location_lat") is not None:
            loc["lat"] = rt.meta.get("location_lat")
        if loc.get("lng") is None and rt.meta.get("location_lng") is not None:
            loc["lng"] = rt.meta.get("location_lng")
        if loc.get("address") is None and rt.meta.get("location_address"):
            loc["address"] = rt.meta.get("location_address")
        rt.vehicle_state.data["location"] = loc

    def _seed_location_from_meta(self, vehicle_id: str) -> None:
        self._apply_location_to_runtime(vehicle_id)

    @staticmethod
    def _empty_rest_slices() -> dict[str, Any]:
        return {
            "notices": {"unread": 0},
            "maintain": {
                "last_project": None,
                "last_date": None,
                "last_odometer": None,
                "next_date": None,
                "next_odometer": None,
            },
            "firmware": {
                "available": False,
                "offered_version": None,
                "upgrading": False,
            },
        }

    def _seed_rest_slices_from_meta(self, vehicle_id: str) -> None:
        """Hydrate notice/maintain/firmware VehicleState from persisted meta."""
        rt = self._vehicles.get(str(vehicle_id))
        if rt is None:
            return
        meta = self.store.get_vehicle_meta(vehicle_id)
        rt.meta = meta
        data = rt.vehicle_state.data
        for key, empty in self._empty_rest_slices().items():
            if key not in data or not isinstance(data.get(key), dict):
                data[key] = dict(empty)
        if meta.get("notice_unread") is not None:
            try:
                data["notices"]["unread"] = int(meta["notice_unread"])
            except (TypeError, ValueError):
                pass
        maintain = data["maintain"]
        for field_name, meta_key in (
            ("last_project", "maintain_last_project"),
            ("last_date", "maintain_last_date"),
            ("last_odometer", "maintain_last_odometer"),
            ("next_date", "maintain_next_date"),
            ("next_odometer", "maintain_next_odometer"),
        ):
            if meta_key in meta:
                maintain[field_name] = meta.get(meta_key)
        firmware = data["firmware"]
        if "firmware_available" in meta:
            firmware["available"] = bool(meta.get("firmware_available"))
        if "firmware_offered_version" in meta:
            firmware["offered_version"] = meta.get("firmware_offered_version")
        if "firmware_upgrading" in meta:
            firmware["upgrading"] = bool(meta.get("firmware_upgrading"))

    async def _probe_location(self, vehicle_id: str, *, force: bool = False) -> None:
        """One locate call; update capability + coords. Never raises for setup."""
        rt = self._vehicles.get(str(vehicle_id))
        if rt is None or not rt.device_sn:
            return
        meta = self.store.get_vehicle_meta(vehicle_id)
        if meta.get("location_supported") is False and not force:
            return
        try:
            result = await self.api.device_locate(
                vehicle_id=vehicle_id, device_sn=rt.device_sn
            )
        except AuthError:
            raise
        except Exception:
            _LOGGER.exception(
                f"deviceLocate probe failed vehicle={partial_id(vehicle_id)}"
            )
            return
        code = str(result.get("code") or "")
        supported = interpret_device_locate_code(code)
        if supported is None:
            _LOGGER.debug(
                f"deviceLocate inconclusive vehicle={partial_id(vehicle_id)} "
                f"code={code}"
            )
            return
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        lat = lng = address = None
        updated = None
        if supported and code in (OK_CODE, "0") and data:
            try:
                lat = float(data["lat"]) if data.get("lat") is not None else None
                lng = float(data["lng"]) if data.get("lng") is not None else None
            except (TypeError, ValueError):
                lat = lng = None
            address = data.get("address")
            if isinstance(address, str):
                address = address.strip() or None
            else:
                address = None
            if lat is not None and lng is not None:
                updated = time.time()
        self.store.update_vehicle_location_meta(
            vehicle_id,
            supported=supported,
            lat=lat,
            lng=lng,
            address=address,
            updated=updated,
        )
        self._apply_location_to_runtime(vehicle_id, lat=lat, lng=lng, address=address)
        _LOGGER.info(
            f"location capability vehicle={partial_id(vehicle_id)} "
            f"supported={supported} code={code}"
        )
        self._maybe_notify_spec_changes(vehicle_id)

    async def _probe_all_locations(self) -> None:
        for vid in list(self._vehicles):
            try:
                await self._probe_location(vid)
            except AuthError:
                raise
            except Exception:
                _LOGGER.exception(f"location probe skipped vehicle={partial_id(vid)}")

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
        _LOGGER.info("coordinator starting")
        await self.store.async_load()
        _LOGGER.debug(f"store loaded entry_id={partial_id(self.entry.entry_id)}")
        try:
            _LOGGER.debug("async_start → api.sync_server_time")
            await self.api.sync_server_time()
            _LOGGER.debug("async_start → api.login")
            await self.api.login()
            _LOGGER.debug("async_start → api.async_list_vehicles force=true")
            rows = await self.api.async_list_vehicles(force=True)
            if not rows:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cannot_connect",
                )
            self._sync_vehicles_from_rows(rows)
            if not self._vehicles:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="cannot_connect",
                )
        except Exception as err:
            if _is_auth_error(err):
                await self._async_handle_auth_failure(err, source="setup")
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise
        self._stop.clear()
        for vid in list(self._vehicles):
            _LOGGER.debug(f"_start_ws vehicle={vid}")
            self._start_ws(vid)
            self._async_refresh_device(vid)
            self._seed_location_from_meta(vid)
            self._seed_rest_slices_from_meta(vid)
        self._publish_data()
        await self._async_wait_for_stream()
        try:
            await self._probe_all_locations()
        except AuthError as err:
            await self._async_handle_auth_failure(err, source="location_probe")
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            ) from err
        try:
            await self._probe_all_firmware()
        except AuthError as err:
            await self._async_handle_auth_failure(err, source="firmware_probe")
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            ) from err
        self._publish_data()
        for vid, rt in self._vehicles.items():
            rt.spec_keys = self.current_spec_keys(vid)
        self._caps_task = self.hass.async_create_background_task(
            self._caps_refresh_loop(), name=f"{DOMAIN}_caps"
        )
        self._location_task = self.hass.async_create_background_task(
            self._location_poll_loop(), name=f"{DOMAIN}_location"
        )
        self._notice_task = self.hass.async_create_background_task(
            self._notice_poll_loop(), name=f"{DOMAIN}_notice"
        )
        self._maintain_task = self.hass.async_create_background_task(
            self._maintain_poll_loop(), name=f"{DOMAIN}_maintain"
        )
        self._firmware_task = self.hass.async_create_background_task(
            self._firmware_poll_loop(), name=f"{DOMAIN}_firmware"
        )
        self._rest_state_task = self.hass.async_create_background_task(
            self._rest_state_poll_loop(), name=f"{DOMAIN}_rest_state"
        )
        _LOGGER.debug(
            f"_caps_refresh_loop task started interval={CAPS_REFRESH_INTERVAL_S}s"
        )
        _LOGGER.debug(
            f"_location_poll_loop task started interval={LOCATION_POLL_INTERVAL_S}s"
        )
        _LOGGER.debug(
            f"_notice_poll_loop task started interval={NOTICE_POLL_INTERVAL_S}s"
        )
        _LOGGER.debug(
            f"_maintain_poll_loop task started interval={MAINTAIN_POLL_INTERVAL_S}s"
        )
        _LOGGER.debug(
            f"_firmware_poll_loop task started interval={FIRMWARE_POLL_INTERVAL_S}s"
        )
        _LOGGER.debug(
            f"_rest_state_poll_loop task started interval={REST_STATE_POLL_INTERVAL_S}s"
        )
        region = require_region_from_entry_data(self.entry.data)
        _LOGGER.info(
            f"CarLinko started region={region} vehicles={len(self._vehicles)} "
            f"ids={[partial_id(vid) for vid in self.vehicle_ids]}"
        )

    async def _async_wait_for_stream(self) -> None:
        """Block setup until at least one vehicle WS session is live."""
        deadline = time.time() + WS_SETUP_TIMEOUT_S
        while time.time() < deadline:
            if any(rt.connected for rt in self._vehicles.values()):
                _LOGGER.debug("_async_wait_for_stream satisfied connected=true")
                return
            if self._stop.is_set():
                return
            await asyncio.sleep(0.25)
        _LOGGER.debug(
            f"_async_wait_for_stream timeout {WS_SETUP_TIMEOUT_S}s connected=false"
        )
        _LOGGER.warning(f"no vehicle websocket connected within {WS_SETUP_TIMEOUT_S}s")
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        )

    def _sync_vehicles_from_rows(self, rows: list[dict[str, Any]]) -> None:
        """Update store + runtime from API list; start/stop WS as needed."""
        metas: dict[str, dict[str, Any]] = {}
        for row in rows:
            vid = vehicle_id_of(row)
            if not vid:
                continue
            metas[vid] = meta_from_api_row(row)
        self.store.set_vehicles(metas)

        old_ids = set(self._vehicles)
        new_ids = set(metas)
        added_ids = new_ids - old_ids
        removed_ids = old_ids - new_ids
        if added_ids or removed_ids:
            _LOGGER.info(
                f"fleet change added={[partial_id(v) for v in sorted(added_ids)]} "
                f"removed={[partial_id(v) for v in sorted(removed_ids)]}"
            )

        for vid in removed_ids:
            _LOGGER.info(f"vehicle removed stopping ws vehicle={vid}")
            self._stop_ws(vid)
            removed_keys = set(self._vehicles[vid].spec_keys)
            del self._vehicles[vid]
            self.store.clear_vehicle_images(vid)
            self._notify_listeners(vid, set(), removed_keys)
            self._async_remove_device(vid)

        for vid in metas:
            # Prefer store meta (includes preserved location_*).
            meta = self.store.get_vehicle_meta(vid)
            if vid in self._vehicles:
                self._vehicles[vid].meta = meta
                self._vehicles[vid].device_sn = str(meta.get("device_sn") or "")
                self._async_refresh_device(vid)
                self._seed_location_from_meta(vid)
                self._seed_rest_slices_from_meta(vid)
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
                self._seed_location_from_meta(vid)
                self._seed_rest_slices_from_meta(vid)
                self._async_refresh_device(vid)
                plate = meta.get("plate") or "—"
                _LOGGER.info(f"vehicle added starting ws vehicle={vid} plate={plate}")
                if not self._stop.is_set() and self._caps_task is not None:
                    # Already running: start WS and notify entity add for all specs.
                    self._start_ws(vid)
                    self.hass.async_create_task(self._async_probe_new_vehicle(vid))
                    keys = self.current_spec_keys(vid)
                    rt.spec_keys = keys
                    self._notify_listeners(vid, keys, set())

        if old_ids != new_ids:
            # Fleet membership changed — platforms may rebuild wanted set.
            self._notify_listeners("", set(), set())
            self._async_cleanup_stale_devices()

        self._schedule_vehicle_image_ensure(list(metas))

    def _schedule_vehicle_image_ensure(self, vehicle_ids: list[str]) -> None:
        """Kick off CDN fetch/cache for vehicle render angles that need it."""
        for vid in vehicle_ids:
            self.hass.async_create_task(self._ensure_vehicle_images(vid))

    @staticmethod
    def _cdn_log_host(url: str) -> str:
        try:
            parts = urlsplit(url)
            return parts.netloc or "unknown"
        except Exception:
            return "unknown"

    async def _ensure_vehicle_images(self, vehicle_id: str) -> None:
        """Download each render angle once; skip when store already has that URL."""
        vid = str(vehicle_id or "").strip()
        if not vid:
            return
        meta = self.store.get_vehicle_meta(vid)
        published = False
        for angle in IMAGE_ANGLES:
            url = str(meta.get(f"{angle}_image_url") or "").strip()
            if not url:
                continue
            cached = self.store.get_vehicle_image(vid, angle=angle)
            if (
                str(cached.get("url") or "").strip() == url
                and str(cached.get("data") or "").strip()
            ):
                continue
            host = self._cdn_log_host(url)
            _LOGGER.debug(
                f"vehicle image download begin vehicle={vid} angle={angle} host={host}"
            )
            try:
                timeout = ClientTimeout(total=30)
                async with self.api.session.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    status = resp.status
                    if status != 200:
                        _LOGGER.warning(
                            f"vehicle image download failed vehicle={vid} "
                            f"angle={angle} host={host} status={status}"
                        )
                        continue
                    body = await resp.read()
                    if not body:
                        _LOGGER.warning(
                            f"vehicle image download empty vehicle={vid} "
                            f"angle={angle} host={host}"
                        )
                        continue
                    ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(
                        ";"
                    )[0].strip() or "image/jpeg"
                self.store.set_vehicle_image(
                    vid,
                    angle=angle,
                    url=url,
                    content_type=ctype,
                    data_b64=base64.b64encode(body).decode("ascii"),
                )
                _LOGGER.info(
                    f"vehicle image cached vehicle={vid} angle={angle} "
                    f"host={host} bytes={len(body)}"
                )
                published = True
            except Exception:
                _LOGGER.exception(
                    f"vehicle image download error vehicle={vid} "
                    f"angle={angle} host={host}"
                )
        if published:
            self._publish_data()

    async def _async_probe_new_vehicle(self, vehicle_id: str) -> None:
        try:
            await self._probe_location(vehicle_id)
            await self._probe_firmware(vehicle_id)
            self._publish_data()
            self._maybe_notify_spec_changes(vehicle_id)
        except AuthError as err:
            await self._async_handle_auth_failure(err, source="location_probe")
        except Exception:
            _LOGGER.exception(
                f"location probe on fleet add failed vehicle={partial_id(vehicle_id)}"
            )

    def _async_refresh_device(self, vehicle_id: str) -> None:
        """Update DeviceInfo fields when vehicle cache/meta changes."""
        rt = self._vehicles.get(str(vehicle_id))
        if rt is None or not vehicle_id:
            return
        plate = rt.meta.get("plate") or "—"
        model = rt.meta.get("model") or "EV"
        vin = rt.meta.get("vin") or ""
        serial = vin if vin and vin != "—" else (rt.device_sn or None)
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, vehicle_id)})
        if device is None:
            return
        registry.async_update_device(
            device.id,
            name=plate if plate != "—" else model,
            manufacturer="CarLinko",
            model=model,
            serial_number=serial,
        )

    def _async_remove_device(self, vehicle_id: str) -> None:
        """Drop HA device registry entry when a vehicle leaves the account."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, vehicle_id)})
        if device is not None:
            registry.async_update_device(
                device.id, remove_config_entry_id=self.entry.entry_id
            )
            _LOGGER.info(f"device registry removed vehicle={vehicle_id}")
        self._was_available.pop(str(vehicle_id), None)

    def _async_cleanup_stale_devices(self) -> None:
        """Remove devices for this entry that no longer match a live vehicleId."""
        registry = dr.async_get(self.hass)
        live = set(self._vehicles)
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            vids = [ident[1] for ident in device.identifiers if ident[0] == DOMAIN]
            if vids and not any(v in live for v in vids):
                registry.async_update_device(
                    device.id, remove_config_entry_id=self.entry.entry_id
                )

    def _start_ws(self, vehicle_id: str) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None or rt.ws_task is not None:
            return
        rt.stop = asyncio.Event()

        def _on_frame(state: dict, vid: str = vehicle_id) -> None:
            self._handle_frame(vid, dict(state or {}))

        def _on_connected(connected: bool, vid: str = vehicle_id) -> None:
            runtime = self._vehicles.get(vid)
            if runtime is None:
                return
            runtime.connected = connected
            self._log_availability_transition(vid)

        ws = WsClient(
            rt.vehicle_state,
            self.api,
            on_frame=_on_frame,
            on_connected=_on_connected,
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
        restart = False
        try:
            await ws.run(rt.stop)
        except asyncio.CancelledError:
            raise
        except AuthError as err:
            await self._async_handle_auth_failure(err, source="ws")
            _LOGGER.error("WebSocket auth failed; reauthentication required")
        except Exception:
            # Should be rare: WsClient.run reconnects on generic errors.
            _LOGGER.exception(
                f"WebSocket runner stopped unexpectedly for {vehicle_id}; restarting"
            )
            if not self._stop.is_set() and rt is self._vehicles.get(vehicle_id):
                rt.ws_task = None
                restart = True
        finally:
            if rt is self._vehicles.get(vehicle_id) and not restart:
                rt.connected = False
                self._log_availability_transition(vehicle_id)
        if restart:
            self._start_ws(vehicle_id)

    def _log_availability_transition(self, vehicle_id: str) -> None:
        now = self.is_available(vehicle_id)
        was = self._was_available.get(vehicle_id)
        if was is True and now is False:
            _LOGGER.info(f"CarLinko vehicle {vehicle_id} became unavailable")
        if was is False and now is True:
            _LOGGER.info(f"CarLinko vehicle {vehicle_id} became available")
        self._was_available[vehicle_id] = now

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
                await self._async_handle_auth_failure(err, source="caps_refresh")
                _LOGGER.error("Caps refresh auth failed; reauthentication required")
                _LOGGER.debug("_caps_refresh_loop exit auth dead")
                return
            except Exception:
                _LOGGER.exception("vehicle cache refresh failed")

    async def _location_poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=LOCATION_POLL_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass
            for vid, rt in list(self._vehicles.items()):
                meta = self.store.get_vehicle_meta(vid)
                if meta.get("location_supported") is not True:
                    continue
                try:
                    online = await self.api.is_online(vid)
                    if online is False:
                        _LOGGER.debug(
                            f"location poll deferred offline "
                            f"vehicle={partial_id(vid)}"
                        )
                        continue
                    await self._probe_location(vid)
                except AuthError as err:
                    await self._async_handle_auth_failure(err, source="location_poll")
                    _LOGGER.error(
                        "Location poll auth failed; reauthentication required"
                    )
                    return
                except Exception:
                    _LOGGER.exception(f"location poll failed vehicle={partial_id(vid)}")
            self._publish_data()

    @staticmethod
    def _operational_unread(center: dict[str, Any]) -> int:
        total = 0
        for key, notice_type in (
            ("vehicleNoticeVo", 2),
            ("controlNoticeVo", 4),
        ):
            if notice_type not in NOTICE_OPERATIONAL_TYPES:
                continue
            vo = center.get(key)
            if not isinstance(vo, dict):
                continue
            try:
                total += int(vo.get("count") or 0)
            except (TypeError, ValueError):
                continue
        return total

    async def _poll_notices_vehicle(self, vehicle_id: str) -> None:
        """Unread badge + emit events for new operational notices."""
        vid = str(vehicle_id)
        center = await self.api.get_notice_unread_count(vid)
        unread = self._operational_unread(center)
        rt = self._vehicles.get(vid)
        if rt is not None:
            notices = dict(rt.vehicle_state.data.get("notices") or {"unread": 0})
            notices["unread"] = unread
            rt.vehicle_state.data["notices"] = notices

        meta = self.store.get_vehicle_meta(vid)
        seen_raw = meta.get("notice_seen_ids") or []
        seen: set[str] = {str(x) for x in seen_raw if x is not None and str(x)}
        bootstrap = meta.get("notice_last_poll") is None
        prev_unread = self._notice_unread_seen.get(vid)
        should_fetch = bootstrap or prev_unread is None or unread > int(prev_unread)

        if should_fetch:
            for notice_type in NOTICE_OPERATIONAL_TYPES:
                page = await self.api.get_notices(vid, notice_type, page=1, size=20)
                for row in page.get("data") or []:
                    nid = str(row.get("noticeId") or row.get("id") or "")
                    if not nid:
                        continue
                    if nid not in seen:
                        if not bootstrap:
                            self.hass.bus.async_fire(
                                EVENT_NOTICE,
                                {
                                    "vehicle_id": vid,
                                    "notice_id": nid,
                                    "type": notice_type,
                                    "type_name": NOTICE_TYPE_NAMES.get(
                                        notice_type, str(notice_type)
                                    ),
                                    "title": row.get("title"),
                                    "contents": row.get("contents"),
                                    "created_time": row.get("createdTime"),
                                    "is_read": row.get("isRead"),
                                    "operation": row.get("operation"),
                                    "extra": row.get("extra"),
                                },
                            )
                        seen.add(nid)

        ordered = list(seen)
        if len(ordered) > 200:
            ordered = ordered[-200:]
        self.store.update_vehicle_meta(
            vid,
            notice_last_poll=time.time(),
            notice_seen_ids=ordered,
            notice_unread=unread,
        )
        if rt is not None:
            rt.meta = self.store.get_vehicle_meta(vid)

        self._notice_unread_seen[vid] = unread

    async def _notice_poll_loop(self) -> None:
        # First pass shortly after start (bootstrap watermark without flooding events).
        while not self._stop.is_set():
            for vid in list(self._vehicles):
                try:
                    await self._poll_notices_vehicle(vid)
                except AuthError as err:
                    await self._async_handle_auth_failure(err, source="notice_poll")
                    return
                except Exception:
                    _LOGGER.exception(f"notice poll failed vehicle={partial_id(vid)}")
            self._publish_data()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=NOTICE_POLL_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass

    async def _poll_maintain_vehicle(self, vehicle_id: str) -> None:
        vid = str(vehicle_id)
        page = await self.api.get_maintain_page(vid, page=1, size=20)
        items = page.get("data") or []
        row = items[0] if items else {}
        summary = {
            "last_project": row.get("maintainProject"),
            "last_date": row.get("maintainDate"),
            "last_odometer": row.get("maintainExtent"),
            "next_date": row.get("nextMaintainDate"),
            "next_odometer": row.get("nextMaintainExtent"),
        }
        rt = self._vehicles.get(vid)
        if rt is not None:
            rt.vehicle_state.data["maintain"] = dict(summary)
        self.store.update_vehicle_meta(
            vid,
            maintain_last_poll=time.time(),
            maintain_last_project=summary["last_project"],
            maintain_last_date=summary["last_date"],
            maintain_last_odometer=summary["last_odometer"],
            maintain_next_date=summary["next_date"],
            maintain_next_odometer=summary["next_odometer"],
        )
        if rt is not None:
            rt.meta = self.store.get_vehicle_meta(vid)

    async def _maintain_poll_loop(self) -> None:
        while not self._stop.is_set():
            for vid in list(self._vehicles):
                try:
                    await self._poll_maintain_vehicle(vid)
                except AuthError as err:
                    await self._async_handle_auth_failure(err, source="maintain_poll")
                    return
                except Exception:
                    _LOGGER.exception(f"maintain poll failed vehicle={partial_id(vid)}")
            self._publish_data()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=MAINTAIN_POLL_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass

    async def _probe_firmware(self, vehicle_id: str) -> dict[str, Any]:
        vid = str(vehicle_id)
        rt = self._vehicles.get(vid)
        meta = self.store.get_vehicle_meta(vid)
        device_id = str(
            (rt.device_sn if rt else "") or meta.get("device_sn") or ""
        ).strip()
        version = str(
            meta.get("firmware_current_version") or FIRMWARE_VERSION_FALLBACK
        ).strip()
        info = await self.api.get_higher_firmware(device_id, version)
        snapshot = {
            "available": bool(info and info.get("version")),
            "offered_version": (info or {}).get("version") if info else None,
            "upgrading": bool((info or {}).get("upgrading")) if info else False,
        }
        if rt is not None:
            rt.vehicle_state.data["firmware"] = dict(snapshot)
        self.store.update_vehicle_meta(
            vid,
            firmware_last_check=time.time(),
            firmware_available=snapshot["available"],
            firmware_offered_version=snapshot["offered_version"],
            firmware_upgrading=snapshot["upgrading"],
        )
        if rt is not None:
            rt.meta = self.store.get_vehicle_meta(vid)
        return snapshot

    async def _probe_all_firmware(self) -> None:
        for vid in list(self._vehicles):
            try:
                await self._probe_firmware(vid)
            except AuthError:
                raise
            except Exception:
                _LOGGER.exception(f"firmware probe skipped vehicle={partial_id(vid)}")

    async def _firmware_poll_loop(self) -> None:
        # Startup already probed once; wait a full interval before the next.
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=FIRMWARE_POLL_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                await self._probe_all_firmware()
            except AuthError as err:
                await self._async_handle_auth_failure(err, source="firmware_poll")
                return
            self._publish_data()

    async def _poll_rest_state_vehicle(self, vehicle_id: str) -> None:
        """Fetch /user/vehicle/state when WS is down; same blob path as action:6."""
        vid = str(vehicle_id)
        rt = self._vehicles.get(vid)
        if rt is None or rt.connected:
            return

        d = await self.api.get_vehicle_state(vid)
        code = str(d.get("code") or "")
        if code != OK_CODE:
            _LOGGER.debug(
                f"rest state failed vehicle={partial_id(vid)} "
                f"code={d.get('code')} msg={d.get('msg')}"
            )
            return

        blob = d.get("data")
        if not isinstance(blob, str) or not blob.strip():
            _LOGGER.debug(f"rest state empty blob vehicle={partial_id(vid)}")
            return

        state = rt.vehicle_state.update_data(blob)
        self._handle_frame(vid, dict(state or {}))

    async def _rest_state_poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=REST_STATE_POLL_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass
            for vid in list(self._vehicles):
                try:
                    await self._poll_rest_state_vehicle(vid)
                except AuthError as err:
                    await self._async_handle_auth_failure(err, source="rest_state")
                    return
                except Exception:
                    _LOGGER.exception(
                        f"rest state poll failed vehicle={partial_id(vid)}"
                    )

    def _require_vehicle(self, vehicle_id: str) -> str:
        vid = str(vehicle_id or "").strip()
        if not vid or vid not in self._vehicles:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_vehicle",
                translation_placeholders={"vehicle_id": vid or "—"},
            )
        return vid

    async def async_get_notices(
        self, vehicle_id: str | None = None, *, page: int = 1
    ) -> dict[str, Any]:
        vid = str(vehicle_id or "").strip() or None
        if vid:
            self._require_vehicle(vid)
        items: list[dict[str, Any]] = []
        total = 0
        for notice_type in NOTICE_OPERATIONAL_TYPES:
            result = await self.api.get_notices(vid, notice_type, page=page, size=20)
            total += int(result.get("total") or 0)
            for row in result.get("data") or []:
                items.append(
                    {
                        **row,
                        "type": notice_type,
                        "type_name": NOTICE_TYPE_NAMES.get(
                            notice_type, str(notice_type)
                        ),
                    }
                )
        return {"total": total, "items": items}

    async def async_get_maintain_history(
        self,
        vehicle_id: str,
        *,
        query_key: str = "",
        page: int = 1,
    ) -> dict[str, Any]:
        vid = self._require_vehicle(vehicle_id)
        result = await self.api.get_maintain_page(
            vid, query_key=query_key, page=page, size=20
        )
        return {
            "total": int(result.get("total") or 0),
            "items": result.get("data") or [],
        }

    async def async_get_maintain_details(
        self, vehicle_id: str, maintain_id: str
    ) -> dict[str, Any]:
        self._require_vehicle(vehicle_id)
        mid = str(maintain_id or "").strip()
        if not mid:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="missing_maintain_id",
            )
        return await self.api.get_maintain_details(mid)

    async def async_check_firmware(self, vehicle_id: str) -> dict[str, Any]:
        vid = self._require_vehicle(vehicle_id)
        snapshot = await self._probe_firmware(vid)
        self._publish_data()
        return snapshot

    @callback
    def _handle_frame(self, vehicle_id: str, state: dict) -> None:
        rt = self._vehicles.get(vehicle_id)
        if rt is None:
            return
        rt.last_update_ts = float(state.get("updated_ts") or time.time())
        self._publish_data()
        self._log_availability_transition(vehicle_id)
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
        if added or removed:
            _LOGGER.info(
                f"capability change vehicle={partial_id(vehicle_id)} "
                f"added={sorted(added)} removed={sorted(removed)}"
            )
        rt.spec_keys = new_keys
        self._notify_listeners(vehicle_id, added, removed)

    async def async_send_control(
        self,
        opcode: str,
        timeout: int = 20,
        *,
        vehicle_id: str,
    ) -> dict:
        vid = str(vehicle_id or "").strip()
        if not vid:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={"error": "vehicle_id required"},
            )
        rt = self._vehicles.get(vid)
        meta = self.store.get_vehicle_meta(vid)
        dsn = str((rt.device_sn if rt else "") or meta.get("device_sn") or "").strip()
        if not dsn:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={"error": "device_sn missing for vehicle"},
            )
        _LOGGER.debug(f"async_send_control opcode={opcode} vehicle={partial_id(vid)}")
        try:
            result = await self.api.send_control(
                opcode, timeout=timeout, vehicle_id=vid, device_sn=dsn
            )
        except Exception as err:
            if _is_auth_error(err):
                await self._async_handle_auth_failure(err, source="control")
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
            _LOGGER.warning(
                f"remote control stale token vehicle={partial_id(vid)} code={code}"
            )
            await self._async_handle_auth_failure(
                AuthError(f"token stale (code={code})"), source="control"
            )
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            )
        if code and code not in (OK_CODE, "0"):
            _LOGGER.warning(
                f"remote control failed vehicle={partial_id(vid)} opcode={opcode} "
                f"code={code} msg={result.get('msg')}"
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={
                    "error": f"code={code} msg={result.get('msg')}"
                },
            )
        _LOGGER.debug("async_send_control result ok")
        return result

    async def async_stop(self) -> None:
        ws_count = sum(1 for rt in self._vehicles.values() if rt.ws_task)
        caps = 1 if self._caps_task else 0
        loc = 1 if self._location_task else 0
        notice = 1 if self._notice_task else 0
        maintain = 1 if self._maintain_task else 0
        firmware = 1 if self._firmware_task else 0
        rest_state = 1 if self._rest_state_task else 0
        _LOGGER.info(f"coordinator stopping vehicles={len(self._vehicles)}")
        _LOGGER.debug(
            f"async_stop cancel ws tasks count={ws_count} "
            f"caps_task={caps} location_task={loc} notice_task={notice} "
            f"maintain_task={maintain} firmware_task={firmware} "
            f"rest_state_task={rest_state}"
        )
        self._stop.set()
        tasks: list[asyncio.Task] = []
        for vid in list(self._vehicles):
            rt = self._vehicles[vid]
            rt.stop.set()
            if rt.ws_task:
                rt.ws_task.cancel()
                tasks.append(rt.ws_task)
                rt.ws_task = None
        for attr in (
            "_caps_task",
            "_location_task",
            "_notice_task",
            "_maintain_task",
            "_firmware_task",
            "_rest_state_task",
        ):
            task = getattr(self, attr)
            if task:
                task.cancel()
                tasks.append(task)
                setattr(self, attr, None)
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                _LOGGER.exception("task failed during shutdown")
        _LOGGER.info("coordinator stopped")

    async def _async_handle_auth_failure(
        self, err: Exception, *, source: str = "unknown"
    ) -> None:
        """Clear dead token and prompt HA reauthentication."""
        _LOGGER.debug(
            f"_async_handle_auth_failure clear token "
            f"entry_id={partial_id(self.entry.entry_id)}"
        )
        _LOGGER.warning(f"auth failure source={source} {err}")
        _LOGGER.error(
            f"starting reauth flow entry_id={partial_id(self.entry.entry_id)}"
        )
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
    store = CarlinkoStore(
        hass,
        ha_store=Store(hass, STORAGE_VERSION, ha_storage_key(entry.entry_id)),
    )
    session = async_get_clientsession(hass)
    return CarlinkoCoordinator(hass, entry, store, session)
