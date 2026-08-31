"""Location capability, store merge, device_tracker entity."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

from custom_components.carlinko.common.helpers import interpret_device_locate_code
from custom_components.carlinko.device_tracker import CarlinkoDeviceTracker
from custom_components.carlinko.managers.store import CarlinkoStore
from custom_components.carlinko.models.entity_specs import (
    ENTITY_SPECS,
    get_entity_specs,
)
from homeassistant.components.device_tracker import SourceType


def test_interpret_device_locate_code() -> None:
    assert interpret_device_locate_code("0000") is True
    assert interpret_device_locate_code("0") is True
    assert interpret_device_locate_code("50049") is False
    assert interpret_device_locate_code("50052") is True
    assert interpret_device_locate_code("50053") is True
    assert interpret_device_locate_code("-1") is None
    assert interpret_device_locate_code("") is None
    assert interpret_device_locate_code(None) is None
    assert interpret_device_locate_code("boom") is None


def test_location_spec_gated_by_cap() -> None:
    assert any(
        s.key == "location" and s.platform == "device_tracker" for s in ENTITY_SPECS
    )
    assert not get_entity_specs(platform="device_tracker", caps={})
    specs = get_entity_specs(platform="device_tracker", caps={"location": True})
    assert [s.key for s in specs] == ["location"]


def test_set_vehicles_preserves_location_meta() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        store.set_vehicles(
            {
                "v1": {
                    "device_sn": "s1",
                    "plate": "AAA",
                    "model": "J5",
                    "vin": "VIN1",
                    "location_supported": True,
                    "location_lat": 1.5,
                    "location_lng": 2.5,
                    "location_address": "Somewhere",
                }
            }
        )
        store.set_vehicles(
            {
                "v1": {
                    "device_sn": "s1",
                    "plate": "AAA-NEW",
                    "model": "J5",
                    "vin": "VIN1",
                }
            }
        )
        meta = store.get_vehicle_meta("v1")
        assert meta["plate"] == "AAA-NEW"
        assert meta["location_supported"] is True
        assert meta["location_lat"] == 1.5
        assert meta["location_lng"] == 2.5
        assert meta["location_address"] == "Somewhere"
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_update_vehicle_location_meta() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        store.set_vehicles(
            {"v1": {"device_sn": "s1", "plate": "P", "model": "M", "vin": "V"}}
        )
        store.update_vehicle_location_meta(
            "v1",
            supported=True,
            lat=32.1,
            lng=34.8,
            address="Tel Aviv",
            updated=123.0,
        )
        meta = store.get_vehicle_meta("v1")
        assert meta["location_supported"] is True
        assert meta["location_lat"] == 32.1
        assert meta["location_lng"] == 34.8
        assert meta["location_address"] == "Tel Aviv"
        assert meta["location_updated"] == 123.0
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_device_tracker_coords_and_unavailable() -> None:
    coordinator = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "plate": "P",
        "model": "M",
        "vin": "V",
    }
    coordinator.is_available.return_value = True
    coordinator.vehicle_data.return_value = {
        "vehicle": {"plate": "P", "model": "M"},
        "location": {"lat": None, "lng": None, "address": None},
    }
    spec = next(s for s in ENTITY_SPECS if s.key == "location")
    entity = CarlinkoDeviceTracker(coordinator, spec, "veh-1")
    assert entity.available is False
    assert entity.latitude is None
    assert entity.source_type == SourceType.GPS

    coordinator.vehicle_data.return_value = {
        "vehicle": {"plate": "P", "model": "M"},
        "location": {"lat": 32.0, "lng": 34.0, "address": "Home"},
    }
    assert entity.available is True
    assert entity.latitude == 32.0
    assert entity.longitude == 34.0
    assert entity.location_name == "Home"
