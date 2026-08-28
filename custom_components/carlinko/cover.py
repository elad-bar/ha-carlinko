"""CarLinko covers (windows / sunroof / liftgate)."""

from __future__ import annotations

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
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
        hass, entry, coordinator, "cover", async_add_entities, CarlinkoCover
    )


class CarlinkoCover(CarlinkoEntity, CoverEntity):
    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        )

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
