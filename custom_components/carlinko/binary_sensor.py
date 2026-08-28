"""CarLinko binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
        "binary_sensor",
        async_add_entities,
        CarlinkoBinarySensor,
    )


class CarlinkoBinarySensor(CarlinkoEntity, BinarySensorEntity):
    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        value = self._state_value()
        if value is None:
            return None
        return bool(value)
