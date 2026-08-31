"""CarLinko device tracker (GPS via /maps/deviceLocate)."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .common.base_entity import CarlinkoEntity
from .common.entity_setup import async_setup_entities
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import EntitySpec

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = entry.runtime_data
    async_setup_entities(
        hass,
        entry,
        coordinator,
        "device_tracker",
        async_add_entities,
        CarlinkoDeviceTracker,
    )


class CarlinkoDeviceTracker(CarlinkoEntity, TrackerEntity):
    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)

    def _location(self) -> dict:
        raw = self._state_value()
        return dict(raw) if isinstance(raw, dict) else {}

    @property
    def available(self) -> bool:
        loc = self._location()
        lat, lng = loc.get("lat"), loc.get("lng")
        if lat is None or lng is None:
            return False
        return super().available

    @property
    def latitude(self) -> float | None:
        lat = self._location().get("lat")
        try:
            return float(lat) if lat is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def longitude(self) -> float | None:
        lng = self._location().get("lng")
        try:
            return float(lng) if lng is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def location_name(self) -> str | None:
        address = self._location().get("address")
        return str(address) if address else None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS
