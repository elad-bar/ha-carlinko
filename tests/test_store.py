"""Store multi-vehicle map tests (no HA runtime)."""

from __future__ import annotations

import os
import tempfile

import pytest

from custom_components.carlinko.managers.store import CarlinkoStore


def test_meta_from_api_row_includes_api_row() -> None:
    from custom_components.carlinko.managers.api_client import meta_from_api_row

    row = {
        "vehicleId": "v1",
        "deviceId": "sn-1",
        "licenseNumber": "P",
        "model": "J5",
        "vin": "VIN1",
        "remoteControls": {"commandList": []},
    }
    meta = meta_from_api_row(row)
    assert meta["api_row"]["remoteControls"] == {"commandList": []}
    assert meta["api_row"]["vehicleId"] == "v1"


def test_set_vehicles_map_only_no_legacy_mirror() -> None:
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
                },
                "v2": {
                    "device_sn": "s2",
                    "plate": "BBB",
                    "model": "J7",
                    "vin": "VIN2",
                },
            }
        )
        vehicles = store.get_vehicles()
        assert set(vehicles) == {"v1", "v2"}
        assert store.get_vehicle("v2")["plate"] == "BBB"
        assert store.get_vehicle_id() == "v1"
        assert "vehicle_id" not in store.data
        assert "device_sn" not in store.data
        assert "vehicle" not in store.data
        assert vehicles["v1"]["device_sn"] == "s1"
        assert vehicles["v2"]["device_sn"] == "s2"
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_set_vehicles_preserves_nonempty_device_sn() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        store.set_vehicles(
            {"v1": {"device_sn": "s1", "plate": "AAA", "model": "J5", "vin": "VIN1"}}
        )
        store.set_vehicles(
            {"v1": {"device_sn": "", "plate": "AAA-NEW", "model": "J5", "vin": "VIN1"}}
        )
        assert store.get_vehicle_meta("v1")["device_sn"] == "s1"
        assert store.get_vehicle_meta("v1")["plate"] == "AAA-NEW"
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_get_vehicles_legacy_read() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        store.data = {
            "vehicle_id": "legacy-1",
            "device_sn": "legacy-sn",
            "vehicle": {"plate": "P", "model": "M", "vin": "V"},
        }
        vehicles = store.get_vehicles()
        assert vehicles["legacy-1"]["device_sn"] == "legacy-sn"
        assert vehicles["legacy-1"]["plate"] == "P"
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_cost_config_amounts() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        cfg = store.get_cost_config()
        assert cfg == {"tariff": 0, "petrol_price": 0.0, "petrol_kml": 0.0}
        assert "currency" not in cfg
        assert store.set_cost_config("tariff", 100)["ok"]
        assert store.get_cost_config()["tariff"] == 100.0
        assert store.set_cost_config("tariff", 1.25)["ok"]
        assert store.get_cost_config()["tariff"] == 1.25
        assert store.set_cost_config("petrol_price", 0)["ok"]
        assert store.get_cost_config()["petrol_price"] == 0.0
        assert store.set_cost_config("petrol_price", 2.35)["ok"]
        assert store.get_cost_config()["petrol_price"] == 2.35
    finally:
        if os.path.isfile(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_async_remove_file_store() -> None:
    path = tempfile.mktemp(suffix=".json")
    store = CarlinkoStore(path=path)
    store.set_token("secret-token")
    assert os.path.isfile(path)
    await store.async_remove()
    assert not os.path.isfile(path)
    assert store.data == {}
