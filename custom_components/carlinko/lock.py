"""CarLinko lock."""
from __future__ import annotations

from homeassistant.components.lock import LockEntity
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
        hass, coordinator, "lock", async_add_entities, CarlinkoLock
    )


class CarlinkoLock(CarlinkoEntity, LockEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)

    @property
    def is_locked(self) -> bool | None:
        value = self._state_value()
        if value is None:
            return None
        return str(value).upper() == "LOCKED"

    async def async_lock(self, **kwargs) -> None:
        await self._async_send_action("lock")

    async def async_unlock(self, **kwargs) -> None:
        await self._async_send_action("unlock")
