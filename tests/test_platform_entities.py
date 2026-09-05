"""Smoke tests for each platform entity class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.carlinko.binary_sensor import CarlinkoBinarySensor
from custom_components.carlinko.button import CarlinkoButton
from custom_components.carlinko.climate import CarlinkoClimate
from custom_components.carlinko.cover import CarlinkoCover
from custom_components.carlinko.device_tracker import CarlinkoDeviceTracker
from custom_components.carlinko.lock import CarlinkoLock
from custom_components.carlinko.models.entity_specs import ENTITY_SPECS
from custom_components.carlinko.number import CarlinkoNumber
from custom_components.carlinko.select import CarlinkoSelect
from custom_components.carlinko.sensor import CarlinkoSensor
from custom_components.carlinko.switch import CarlinkoSwitch
from homeassistant.components.climate import HVACMode
from homeassistant.components.device_tracker import SourceType


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


def test_device_tracker_gps() -> None:
    coordinator = _coordinator(
        location={"lat": 1.0, "lng": 2.0, "address": "A"},
    )
    entity = CarlinkoDeviceTracker(coordinator, _spec("location"), "veh-1")
    assert entity.source_type == SourceType.GPS
    assert entity.latitude == 1.0
    assert entity.longitude == 2.0
    assert entity.location_name == "A"


@pytest.mark.asyncio
async def test_image_front_from_store() -> None:
    import base64
    from unittest.mock import patch

    from custom_components.carlinko.image import CarlinkoImage

    coordinator = _coordinator()
    coordinator.vehicle_ids = ["veh-1"]
    coordinator.hass = MagicMock()
    coordinator.store.get_vehicle_image.return_value = {
        "url": "https://cdn.example/f.png",
        "content_type": "image/png",
        "data": base64.b64encode(b"PNG").decode("ascii"),
        "updated": 1700000000.0,
    }
    with patch(
        "homeassistant.components.image.get_async_client", return_value=MagicMock()
    ):
        entity = CarlinkoImage(coordinator, _spec("vehicle_front"), "veh-1")
    assert entity._attr_translation_key == "vehicle_front"
    assert entity._angle == "front"
    assert entity.content_type == "image/png"
    assert await entity.async_image() == b"PNG"
    assert entity.available is True
    coordinator.store.get_vehicle_image.assert_called_with("veh-1", angle="front")


@pytest.mark.asyncio
async def test_image_side_and_top_angles() -> None:
    import base64
    from unittest.mock import patch

    from custom_components.carlinko.image import CarlinkoImage

    coordinator = _coordinator()
    coordinator.vehicle_ids = ["veh-1"]
    coordinator.hass = MagicMock()

    def _img(vid, angle="front"):
        return {
            "url": f"https://cdn.example/{angle}.png",
            "content_type": "image/png",
            "data": base64.b64encode(angle.encode()).decode("ascii"),
            "updated": 1700000000.0,
        }

    coordinator.store.get_vehicle_image.side_effect = _img
    with patch(
        "homeassistant.components.image.get_async_client", return_value=MagicMock()
    ):
        side = CarlinkoImage(coordinator, _spec("vehicle_side"), "veh-1")
        top = CarlinkoImage(coordinator, _spec("vehicle_top"), "veh-1")
    assert side._angle == "side"
    assert top._angle == "top"
    assert await side.async_image() == b"side"
    assert await top.async_image() == b"top"
