"""CarLinko number entities (cost knobs)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .common.base_entity import CarlinkoEntity
from .common.entity_setup import async_setup_entities
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import EntitySpec

PARALLEL_UPDATES = 1

_LIMITS = {
    "tariff": (0, 1e7, 1),
    "petrol_price": (0, 1e7, 1),
    "petrol_kml": (0, 100, 0.1),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = entry.runtime_data
    async_setup_entities(
        hass, entry, coordinator, "number", async_add_entities, CarlinkoNumber
    )


class CarlinkoNumber(CarlinkoEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)
        lo, hi, step = _LIMITS.get(spec.config_key or spec.key, (0, 1e7, 1))
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step

    @property
    def native_value(self) -> float | None:
        value = self._state_value()
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        key = self.spec.config_key or self.spec.key
        result = self.coordinator.store.set_cost_config(key, value)
        if not result.get("ok"):
            raise ValueError(result.get("error") or "set failed")
        await self.coordinator.store.async_save()
        self.async_write_ha_state()
