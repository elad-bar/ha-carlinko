"""Smoke tests for each platform entity class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.carlinko.binary_sensor import CarlinkoBinarySensor
from custom_components.carlinko.button import CarlinkoButton
from custom_components.carlinko.climate import CarlinkoClimate
from custom_components.carlinko.cover import CarlinkoCover
from custom_components.carlinko.lock import CarlinkoLock
from custom_components.carlinko.models.entity_specs import ENTITY_SPECS
from custom_components.carlinko.number import CarlinkoNumber
from custom_components.carlinko.select import CarlinkoSelect
from custom_components.carlinko.sensor import CarlinkoSensor
from custom_components.carlinko.switch import CarlinkoSwitch
from homeassistant.components.climate import HVACMode


def _spec(key: str):
    return next(s for s in ENTITY_SPECS if s.key == key)


def _coordinator(**vehicle_data_extra) -> MagicMock:
    coordinator = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "plate": "P",
        "model": "M",
        "vin": "V",
    }
    coordinator.store.get_cost_config.return_value = {"tariff": 1.0}
    coordinator.store.set_cost_config.return_value = {"ok": True}
    coordinator.store.async_save = AsyncMock()
    coordinator.caps_for.return_value = {
        "ac": {"switch": True, "temp": True, "min": 16, "max": 30, "step": 1}
    }
    data = {
        "vehicle": {"plate": "P", "model": "M", "vin": "V"},
        "unlocked": False,
        "engine_on": True,
        "windows": False,
        "ac_on": True,
        "ac_temp_calculated": 22,
        "seat_heat_l": 1,
        "online": True,
        "battery": 77,
        **vehicle_data_extra,
    }
    coordinator.vehicle_data.return_value = data
    coordinator.async_send_control = AsyncMock()
    coordinator.is_available.return_value = True
    return coordinator


def test_sensor_native_value() -> None:
    entity = CarlinkoSensor(_coordinator(), _spec("battery"), "veh-1")
    assert entity._attr_translation_key == "battery"
    assert entity.unique_id == "carlinko_veh-1_battery"
    assert entity.native_value == 77


def test_binary_sensor_is_on() -> None:
    entity = CarlinkoBinarySensor(_coordinator(online=True), _spec("online"), "veh-1")
    assert entity._attr_translation_key == "online"
    assert entity.is_on is True


@pytest.mark.asyncio
async def test_number_set_value() -> None:
    coordinator = _coordinator()
    entity = CarlinkoNumber(coordinator, _spec("tariff"), "veh-1")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    assert entity._attr_translation_key == "tariff"
    assert entity._attr_native_step == 0.01
    assert entity.native_value == 1.0
    await entity.async_set_native_value(2.5)
    coordinator.store.set_cost_config.assert_called_once_with("tariff", 2.5)
    coordinator.store.async_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_lock_unlock() -> None:
    coordinator = _coordinator()
    entity = CarlinkoLock(coordinator, _spec("lock"), "veh-1")
    assert entity.is_locked is True
    await entity.async_unlock()
    coordinator.async_send_control.assert_awaited_with("740200", vehicle_id="veh-1")
    await entity.async_lock()
    assert coordinator.async_send_control.await_count == 2


@pytest.mark.asyncio
async def test_climate_turn_off() -> None:
    coordinator = _coordinator()
    entity = CarlinkoClimate(coordinator, _spec("climate"), "veh-1")
    assert entity.target_temperature == 22.0
    await entity.async_set_hvac_mode(HVACMode.OFF)
    coordinator.async_send_control.assert_awaited_with("741000", vehicle_id="veh-1")


@pytest.mark.asyncio
async def test_cover_open_close() -> None:
    coordinator = _coordinator()
    entity = CarlinkoCover(coordinator, _spec("windows"), "veh-1")
    assert entity.is_closed is True
    await entity.async_open_cover()
    coordinator.async_send_control.assert_awaited_with("740600", vehicle_id="veh-1")


@pytest.mark.asyncio
async def test_button_press() -> None:
    coordinator = _coordinator()
    entity = CarlinkoButton(coordinator, _spec("find"), "veh-1")
    await entity.async_press()
    coordinator.async_send_control.assert_awaited_with("740400", vehicle_id="veh-1")


@pytest.mark.asyncio
async def test_switch_turn_on_off() -> None:
    coordinator = _coordinator()
    entity = CarlinkoSwitch(coordinator, _spec("engine"), "veh-1")
    assert entity.is_on is True
    await entity.async_turn_off()
    coordinator.async_send_control.assert_awaited_with("740800", vehicle_id="veh-1")


@pytest.mark.asyncio
async def test_select_option() -> None:
    coordinator = _coordinator()
    entity = CarlinkoSelect(coordinator, _spec("seat_heat_l"), "veh-1")
    assert entity.current_option == "l1"
    await entity.async_select_option("off")
    coordinator.async_send_control.assert_awaited_with("741500", vehicle_id="veh-1")
