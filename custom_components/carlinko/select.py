"""CarLinko select entities (gear / seat levels)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .models.base_entity import CarlinkoEntity
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
        hass, entry, coordinator, "select", async_add_entities, CarlinkoSelect
    )


class CarlinkoSelect(CarlinkoEntity, SelectEntity):
    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)
        options = list(spec.options or ())
        if not options and spec.commands:
            options = list(spec.commands.keys())
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        value = self._state_value()
        if value is None:
            return None
        text = str(value)
        if text in self._attr_options:
            return text
        return None

    async def async_select_option(self, option: str) -> None:
        await self._async_send_action(option)
