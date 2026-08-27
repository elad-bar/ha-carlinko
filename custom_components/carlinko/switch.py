"""CarLinko switches."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .models.base_entity import CarlinkoEntity
from .common.entity_setup import async_setup_entities
from .common.consts import DOMAIN
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import EntitySpec

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_setup_entities(
        hass, coordinator, "switch", async_add_entities, CarlinkoSwitch
    )


class CarlinkoSwitch(CarlinkoEntity, SwitchEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)

    @property
    def is_on(self) -> bool | None:
        value = self._state_value()
        if value is None:
            # Fall back to related binary paths for command-only switches.
            state = self.coordinator.data or {}
            if self.spec.key == "engine":
                return bool(state.get("engine_on"))
            if self.spec.key == "defrost_cmd":
                return bool(state.get("defrost"))
            if self.spec.key == "purify":
                return bool(state.get("purify"))
            return None
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("on", "true", "1")

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_send_action("on")

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_send_action("off")
