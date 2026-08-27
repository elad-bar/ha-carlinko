"""Coordinator auth-failure tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.common.consts import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from custom_components.carlinko.managers.coordinator import CarlinkoCoordinator
from custom_components.carlinko.managers.store import CarlinkoStore
from custom_components.carlinko.models.exceptions import AuthError


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "sea",
        },
    )


@pytest.mark.asyncio
async def test_async_start_auth_error(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = CarlinkoStore(hass, entry.entry_id)
    store.data = {"token": "dead"}
    session = MagicMock()
    coordinator = CarlinkoCoordinator(hass, entry, store, session)

    with (
        patch.object(coordinator.api, "login", new_callable=AsyncMock) as login,
        patch.object(entry, "async_start_reauth") as start_reauth,
    ):
        login.side_effect = AuthError("login failed")
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator.async_start()
        start_reauth.assert_called_once_with(hass)
        assert coordinator.api.token == ""
        assert store.data.get("token") == ""


@pytest.mark.asyncio
async def test_async_send_control_auth_error(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = CarlinkoStore(hass, entry.entry_id)
    store.data = {"token": "dead", "vehicle_id": "v1", "device_sn": "s1"}
    session = MagicMock()
    coordinator = CarlinkoCoordinator(hass, entry, store, session)
    coordinator.api.token = "dead"
    coordinator.api.vehicle_id = "v1"
    coordinator.api.device_sn = "s1"

    with (
        patch.object(
            coordinator.api, "send_control", new_callable=AsyncMock
        ) as send_control,
        patch.object(entry, "async_start_reauth") as start_reauth,
    ):
        send_control.side_effect = AuthError("relogin failed")
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator.async_send_control("740100")
        start_reauth.assert_called_once_with(hass)
