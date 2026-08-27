"""CarLinko sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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

_DEVICE_CLASS = {v.value: v for v in SensorDeviceClass}
_STATE_CLASS = {v.value: v for v in SensorStateClass}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_setup_spec_platform(
        hass, coordinator, "sensor", async_add_entities, CarlinkoSensor
    )


class CarlinkoSensor(CarlinkoEntity, SensorEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        if spec.unit:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.device_class:
            self._attr_device_class = _DEVICE_CLASS.get(spec.device_class)
        if spec.state_class:
            self._attr_state_class = _STATE_CLASS.get(spec.state_class)
        if spec.options:
            self._attr_options = list(spec.options)

    @property
    def native_value(self):
        return self._state_value()
