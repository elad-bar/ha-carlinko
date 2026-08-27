"""CarLinko climate (cool / off)."""
from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
        hass, coordinator, "climate", async_add_entities, CarlinkoClimate
    )


class CarlinkoClimate(CarlinkoEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    _attr_supported_features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator, spec)

    @property
    def hvac_mode(self) -> HVACMode | None:
        value = self._state_value()
        if value == "cool":
            return HVACMode.COOL
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.COOL:
            await self._async_send_action("on")
        else:
            await self._async_send_action("off")

    async def async_turn_on(self) -> None:
        await self._async_send_action("on")

    async def async_turn_off(self) -> None:
        await self._async_send_action("off")
