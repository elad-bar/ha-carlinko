"""Diagnostics redaction smoke tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.common.consts import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from custom_components.carlinko.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_redacts_secrets(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "super-secret",
            CONF_REGION: "sea",
        },
        title="CarLinko (user@example.com)",
    )
    entry.add_to_hass(hass)

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
    }
    coordinator.store.data = {
        "token": "tokensecret",
        "vehicle_id": "vehicle-abcdef",
        "device_sn": "sn-12345678",
        "vin": "VINSECRET",
    }
    coordinator.caps_for.return_value = {"lock": True, "ac": {}}
    coordinator.current_spec_keys.return_value = {"battery", "lock"}

    entry.runtime_data = coordinator

    diag = await async_get_config_entry_diagnostics(hass, entry)
    blob = str(diag)

    assert "super-secret" not in blob
    assert "tokensecret" not in blob
    assert "VINSECRET" not in blob
    assert diag["entry"]["email_domain"] == "example.com"
    assert diag["entry"]["region"] == "sea"
    assert diag["runtime"]["connected"] is True
    assert diag["runtime"]["vehicle_count"] == 1
    assert "battery" in diag["runtime"]["spec_keys"]
    assert CONF_PASSWORD not in diag["data"] or diag["data"].get(CONF_PASSWORD) in (
        None,
        "**REDACTED**",
        "REDACTED",
    )
