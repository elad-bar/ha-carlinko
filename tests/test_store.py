"""Store multi-vehicle map tests (no HA runtime)."""
from __future__ import annotations

import os
import tempfile

import pytest

from custom_components.carlinko.managers.store import CarlinkoStore


def test_set_vehicles_map_and_legacy_mirror() -> None:
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
        assert store.data["vehicle_id"] == "v1"
        assert store.data["device_sn"] == "s1"
    finally:
        if os.path.isfile(path):
            os.unlink(path)


def test_cost_config_amounts() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        cfg = store.get_cost_config()
        assert "tariff" in cfg
        assert "petrol_price" in cfg
        assert "petrol_kml" in cfg
        assert "currency" not in cfg
        assert store.set_cost_config("tariff", 100)["ok"]
        assert store.get_cost_config()["tariff"] == 100
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
