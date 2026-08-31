"""Entity description / resolver / platform semantics (P2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.carlinko.climate import CarlinkoClimate
from custom_components.carlinko.common.entity_descriptions import get_entity_description
from custom_components.carlinko.cover import CarlinkoCover
from custom_components.carlinko.models.entity_specs import (
    ENTITY_SPECS,
    get_entity_specs,
)
from custom_components.carlinko.select import CarlinkoSelect
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed


def _spec(key: str):
    return next(s for s in ENTITY_SPECS if s.key == key)


def test_energy_left_uses_energy_storage() -> None:
    desc = get_entity_description(_spec("energy_left"))
    assert desc.device_class == SensorDeviceClass.ENERGY_STORAGE
    assert desc.state_class == SensorStateClass.MEASUREMENT


def test_tpms_pressure_has_psi_unit() -> None:
    desc = get_entity_description(_spec("tyre_fl"))
    assert desc.device_class == SensorDeviceClass.PRESSURE
    assert desc.native_unit_of_measurement == UnitOfPressure.PSI


def test_distance_sensors_use_kilometers() -> None:
    for key in ("range", "odometer", "wltc_range", "fuel_range", "total_range"):
        desc = get_entity_description(_spec(key))
        assert desc.device_class == SensorDeviceClass.DISTANCE
        assert desc.native_unit_of_measurement == UnitOfLength.KILOMETERS


def test_speed_sensor_uses_kmh() -> None:
    desc = get_entity_description(_spec("speed"))
    assert desc.device_class == SensorDeviceClass.SPEED
    assert desc.native_unit_of_measurement == UnitOfSpeed.KILOMETERS_PER_HOUR
    assert desc.state_class == SensorStateClass.MEASUREMENT


def test_cover_features_open_close_only() -> None:
    coordinator = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "plate": "P",
        "model": "M",
        "vin": "V",
    }
    coordinator.vehicle_data.return_value = {"vehicle": {"plate": "P", "model": "M"}}
    for key in ("windows", "sunroof"):
        cover = CarlinkoCover(coordinator, _spec(key), "veh-1")
        assert cover.supported_features == (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        )
        assert CoverEntityFeature.SET_POSITION not in cover.supported_features


def test_vent_tilt_buttons_in_catalog() -> None:
    keys = {s.key for s in ENTITY_SPECS}
    assert "windows_vent" in keys
    assert "sunroof_tilt" in keys
    vents = get_entity_specs(
        platform="button",
        caps={"windows": {"vent": True}, "sunroof": {"tilt": True}},
    )
    vent_keys = {s.key for s in vents}
    assert "windows_vent" in vent_keys
    assert "sunroof_tilt" in vent_keys
    windows = next(s for s in ENTITY_SPECS if s.key == "windows")
    sunroof = next(s for s in ENTITY_SPECS if s.key == "sunroof")
    assert "vent" not in windows.commands
    assert "tilt" not in sunroof.commands


def test_no_engine_on_binary_in_catalog() -> None:
    assert "engine_on" not in {s.key for s in ENTITY_SPECS}
    assert any(s.key == "engine" and s.platform == "switch" for s in ENTITY_SPECS)


def test_cloud_rest_entities_in_catalog() -> None:
    by_key = {s.key: s for s in ENTITY_SPECS}
    for key in (
        "notice_unread",
        "maintain_last_project",
        "maintain_last_date",
        "maintain_last_odometer",
        "maintain_next_date",
        "maintain_next_odometer",
        "firmware_update_available",
        "firmware_offered_version",
        "firmware_upgrading",
    ):
        assert by_key[key].cloud_rest is True
    assert by_key["firmware_update_available"].platform == "binary_sensor"
    assert by_key["notice_unread"].platform == "sensor"


def test_status_binaries_gated_against_writable_twins() -> None:
    status_keys = {
        "defrost",
        "seat_heat_left",
        "seat_heat_right",
        "seat_vent_left",
        "seat_vent_right",
    }
    writable_keys = {
        "defrost_cmd",
        "seat_heat_l",
        "seat_heat_r",
        "seat_vent_l",
        "seat_vent_r",
    }

    without = {s.key for s in get_entity_specs(caps={})}
    assert status_keys <= without
    assert writable_keys.isdisjoint(without)

    with_caps = {
        "ac": {"defog": True},
        "seats": {"heatL": 3, "heatR": 3, "ventL": 3, "ventR": 3},
    }
    with_keys = {s.key for s in get_entity_specs(caps=with_caps)}
    assert status_keys.isdisjoint(with_keys)
    assert writable_keys <= with_keys


def test_seat_select_current_option_from_blob() -> None:
    coordinator = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "plate": "P",
        "model": "M",
        "vin": "V",
    }
    coordinator.vehicle_data.return_value = {
        "vehicle": {"plate": "P", "model": "M"},
        "seat_heat_l": 1,
    }
    coordinator.store.get_cost_config.return_value = {}
    select = CarlinkoSelect(coordinator, _spec("seat_heat_l"), "veh-1")
    assert select.current_option == "l1"

    coordinator.vehicle_data.return_value = {
        "vehicle": {"plate": "P", "model": "M"},
        "seat_heat_l": 0,
    }
    assert select.current_option == "off"


@pytest.mark.asyncio
async def test_climate_target_temp_from_caps() -> None:
    coordinator = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "plate": "P",
        "model": "M",
        "vin": "V",
    }
    coordinator.caps_for.return_value = {
        "ac": {"temp": True, "min": 16, "max": 30, "step": 1}
    }
    coordinator.vehicle_data.return_value = {
        "vehicle": {"plate": "P", "model": "M"},
        "ac_on": True,
        "ac_temp_calculated": 22,
    }
    coordinator.async_send_control = AsyncMock()

    climate = CarlinkoClimate(coordinator, _spec("climate"), "veh-1")
    assert climate.target_temperature == 22.0
    assert climate.min_temp == 16.0
    assert climate.max_temp == 30.0
    await climate.async_set_temperature(temperature=23)
    coordinator.async_send_control.assert_awaited_once_with(
        "741117", vehicle_id="veh-1"
    )
