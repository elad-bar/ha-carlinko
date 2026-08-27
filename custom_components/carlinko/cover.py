"""CarLinko covers (windows / sunroof / liftgate)."""
from __future__ import annotations

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
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
        hass, coordinator, "cover", async_add_entities, CarlinkoCover
    )


class CarlinkoCover(CarlinkoEntity, CoverEntity):
    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if "vent" in (spec.commands or {}) or "tilt" in (spec.commands or {}):
            features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features

    @property
    def is_closed(self) -> bool | None:
        value = self._state_value()
        if value is None:
            return None
        return str(value).lower() == "closed"

    async def async_open_cover(self, **kwargs) -> None:
        await self._async_send_action("open")

    async def async_close_cover(self, **kwargs) -> None:
        await self._async_send_action("close")
