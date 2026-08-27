"""CarLinko buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CarlinkoCoordinator
from .entity import CarlinkoEntity
from .entity_setup import async_setup_spec_platform
from .protocol.entity_specs import EntitySpec

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_setup_spec_platform(
        hass, coordinator, "button", async_add_entities, CarlinkoButton
    )


class CarlinkoButton(CarlinkoEntity, ButtonEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)

    async def async_press(self) -> None:
        action = "press"
        if self.spec.commands:
            action = next(iter(self.spec.commands.keys()))
        await self._async_send_action(action)
