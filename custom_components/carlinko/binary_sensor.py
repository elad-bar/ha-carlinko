"""CarLinko binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CarlinkoCoordinator
from .entity import CarlinkoEntity
from .entity_setup import async_setup_spec_platform
from .protocol.entity_specs import EntitySpec

PARALLEL_UPDATES = 1

_DEVICE_CLASS = {v.value: v for v in BinarySensorDeviceClass}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_setup_spec_platform(
        hass, coordinator, "binary_sensor", async_add_entities, CarlinkoBinarySensor
    )


class CarlinkoBinarySensor(CarlinkoEntity, BinarySensorEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        if spec.device_class:
            self._attr_device_class = _DEVICE_CLASS.get(spec.device_class)

    @property
    def is_on(self) -> bool | None:
        value = self._state_value()
        if value is None:
            return None
        return bool(value)
