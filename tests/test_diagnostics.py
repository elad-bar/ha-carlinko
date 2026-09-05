"""Diagnostics redaction smoke tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.common.consts import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
)
from custom_components.carlinko.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


def _query_log(vehicle_id=None):
    account = {
        "GET /user/vehicle": {
            "request": {
                "started_at": "2026-09-02T05:00:00Z",
                "finished_at": "2026-09-02T05:00:01Z",
                "http_status": 200,
                "cloud_code": "0000",
                "cloud_msg": "ok",
                "error": None,
            },
            "response": {
                "code": "0000",
                "data": [{"vehicleId": "vehicle-abcdef", "vin": "VINSECRET"}],
            },
        }
    }
    per = {
        "vehicle-abcdef": {
            "POST /maps/deviceLocate": {
                "request": {
                    "http_status": 200,
                    "cloud_code": "0000",
                    "error": None,
                },
                "response": {"code": "0000", "data": {"lat": 1.0}},
            }
        }
    }
    if vehicle_id:
        vid = str(vehicle_id)
        return {"account": account, "vehicles": {vid: per.get(vid, {})}}
    return {"account": account, "vehicles": per}


def _mock_entry_and_coordinator():
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "super-secret",
            CONF_REGION: "sea",
        },
        options={"availability_seconds": 2400},
        title="CarLinko (user@example.com)",
    )

    coordinator = MagicMock()
    coordinator.connected = True
    coordinator.last_update_ts = 123.0
    coordinator.vehicle_ids = ["vehicle-abcdef"]
    coordinator.vehicle_runtime.return_value = MagicMock(
        device_sn="sn-12345678", connected=True, last_update_ts=123.0
    )
    coordinator.store.get_vehicle_meta.return_value = {
        "model": "J5",
        "plate": "ABC123",
        "device_sn": "sn-12345678",
        "vin": "VINSECRET",
    }
    coordinator.store.data = {
        "token": "tokensecret",
        "tariff": 0.12,
        "petrol_price": 6.5,
        "petrol_kml": 14.0,
        "vehicles": {
            "vehicle-abcdef": {
                "model": "J5",
                "plate": "ABC123",
                "device_sn": "sn-12345678",
                "vin": "VINSECRET",
                "api_row": {"vin": "VINSECRET", "brand": "JAECOO"},
            },
            "other-car": {
                "model": "X",
                "vin": "OTHERVIN",
            },
        },
        "vehicle_images": {
            "vehicle-abcdef": {
                "front": {
                    "url": "https://cdn.example/front.png",
                    "content_type": "image/png",
                    "data": "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=",
                    "updated": 1700000000.0,
                },
                "side": {
                    "url": "https://cdn.example/side.png",
                    "content_type": "image/png",
                    "data": "U0lERV9CQVNFNjQ=",
                    "updated": 1700000001.0,
                },
            }
        },
    }
    coordinator.caps_for.return_value = {"lock": True, "ac": {}}
    coordinator.current_spec_keys.return_value = {"battery", "lock"}
    coordinator.vehicle_data.return_value = {
        "battery": 72,
        "vehicle": {"plate": "ABC123", "model": "J5", "vin": "VINSECRET"},
    }
    coordinator.api.token = "tokensecret"
    coordinator.api.time_skew_ms = -120
    coordinator.api.query_log_for_diagnostics.side_effect = _query_log

    entry.runtime_data = coordinator
    return entry, coordinator


@pytest.mark.asyncio
async def test_diagnostics_redacts_secrets() -> None:
    entry, _coordinator = _mock_entry_and_coordinator()

    diag = await async_get_config_entry_diagnostics(None, entry)
    blob = str(diag)

    assert "super-secret" not in blob
    assert "tokensecret" not in blob
    assert "VINSECRET" not in blob
    assert diag["entry"]["data"][CONF_REGION] == "sea"
    assert diag["entry"]["options"]["availability_seconds"] == 2400
    assert "runtime" not in diag
    assert "data" not in diag
    assert diag["account"]["details"]["connected"] is True
    assert diag["account"]["details"]["vehicle_count"] == 1
    assert diag["account"]["details"]["token_present"] is True
    assert "GET /user/vehicle" in diag["account"]["api"]
    vehicle = diag["vehicles"]["vehicle-abcdef"]
    assert vehicle["details"]["battery"] == 72
    assert "lock" in vehicle["details"]["caps_keys"]
    assert "battery" in vehicle["details"]["spec_keys"]
    assert vehicle["details"]["connected"] is True
    assert "POST /maps/deviceLocate" in vehicle["api"]
    assert "vehicle-abcdef" in diag["store"]["vehicles"]
    assert "other-car" in diag["store"]["vehicles"]
    assert "api_row" not in diag["store"]["vehicles"]["vehicle-abcdef"]
    img = diag["store"]["vehicle_images"]["vehicle-abcdef"]
    assert img["front"]["present"] is True
    assert img["front"]["content_type"] == "image/png"
    assert "data" not in img["front"]
    assert img["side"]["present"] is True
    assert "data" not in img["side"]
    assert "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=" not in blob
    assert "U0lERV9CQVNFNjQ=" not in blob
    assert "entity_values" not in vehicle
    assert CONF_PASSWORD not in diag["entry"]["data"] or diag["entry"]["data"].get(
        CONF_PASSWORD
    ) in (None, "**REDACTED**", "REDACTED")


@pytest.mark.asyncio
async def test_device_diagnostics_redacts_and_scopes() -> None:
    entry, _coordinator = _mock_entry_and_coordinator()
    device = MagicMock()
    device.identifiers = {(DOMAIN, "vehicle-abcdef")}

    diag = await async_get_device_diagnostics(None, entry, device)
    blob = str(diag)

    assert "super-secret" not in blob
    assert "tokensecret" not in blob
    assert "VINSECRET" not in blob
    assert "store_vehicle" not in diag
    assert set(diag["store"]["vehicles"]) == {"vehicle-abcdef"}
    assert set(diag["entities"]) == {"vehicle-abcdef"}
    assert set(diag["vehicles"]) == {"vehicle-abcdef"}
    assert "GET /user/vehicle" in diag["account"]["api"]
    assert diag["vehicles"]["vehicle-abcdef"]["details"]["battery"] == 72
    assert diag["store"]["tariff"] == 0.12


@pytest.mark.asyncio
async def test_device_diagnostics_unknown_device() -> None:
    entry, _coordinator = _mock_entry_and_coordinator()
    device = MagicMock()
    device.identifiers = {(DOMAIN, "other-vehicle")}

    diag = await async_get_device_diagnostics(None, entry, device)
    blob = str(diag)

    assert diag["error"] == "unknown_device"
    assert "super-secret" not in blob
    assert "tokensecret" not in blob
    assert "vehicles" not in diag


@pytest.mark.asyncio
async def test_device_diagnostics_missing_identifier() -> None:
    entry, _coordinator = _mock_entry_and_coordinator()
    device = MagicMock()
    device.identifiers = {("other_domain", "x")}

    diag = await async_get_device_diagnostics(None, entry, device)
    assert diag == {"error": "unknown_device"}
