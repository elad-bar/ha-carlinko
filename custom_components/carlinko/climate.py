"""CarLinko climate (cool / off + optional target temperature)."""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .common.base_entity import CarlinkoEntity
from .common.entity_setup import async_setup_entities
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import EntitySpec

PARALLEL_UPDATES = 1

_DEFAULT_MIN_TEMP = 16.0
_DEFAULT_MAX_TEMP = 30.0
_DEFAULT_TEMP_STEP = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = entry.runtime_data
    async_setup_entities(
        hass, entry, coordinator, "climate", async_add_entities, CarlinkoClimate
    )


class CarlinkoClimate(CarlinkoEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]

    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        super().__init__(coordinator, spec, vehicle_id)
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._ac_temp_supported:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_supported_features = features

    @property
    def _ac_caps(self) -> dict:
        return dict(self.coordinator.caps_for(self.vehicle_id).get("ac") or {})

    @property
    def _ac_temp_supported(self) -> bool:
        return bool(self._ac_caps.get("temp"))

    @property
    def min_temp(self) -> float:
        raw = self._ac_caps.get("min")
        try:
            return float(raw) if raw is not None else _DEFAULT_MIN_TEMP
        except (TypeError, ValueError):
            return _DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        raw = self._ac_caps.get("max")
        try:
            return float(raw) if raw is not None else _DEFAULT_MAX_TEMP
        except (TypeError, ValueError):
            return _DEFAULT_MAX_TEMP

    @property
    def target_temperature_step(self) -> float:
        raw = self._ac_caps.get("step")
        try:
            return float(raw) if raw is not None else _DEFAULT_TEMP_STEP
        except (TypeError, ValueError):
            return _DEFAULT_TEMP_STEP

    @property
    def target_temperature(self) -> float | None:
        if not self._ac_temp_supported:
            return None
        state = self.coordinator.vehicle_data(self.vehicle_id)
        raw = state.get("ac_temp_calculated")
        if raw is None:
            raw = state.get("ac_temp")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

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

    async def async_set_temperature(self, **kwargs) -> None:
        if not self._ac_temp_supported:
            return
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            celsius = int(round(float(temp)))
        except (TypeError, ValueError):
            return
        celsius = max(int(self.min_temp), min(int(self.max_temp), celsius))
        opcode = f"7411{celsius:02X}"
        await self.coordinator.async_send_control(opcode, vehicle_id=self.vehicle_id)
