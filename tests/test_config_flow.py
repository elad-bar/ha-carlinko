"""Config flow and reauth tests for CarLinko."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from custom_components.carlinko.protocol.entity_specs import ENTITY_SPECS
from custom_components.carlinko.protocol.entity_values import EntityValueResolver
from custom_components.carlinko.protocol.exceptions import AuthError


@pytest.mark.asyncio
async def test_config_flow_user_success(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.carlinko.config_flow.ApiClient.login",
        new_callable=AsyncMock,
        return_value="token",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "secret",
                CONF_REGION: "sea",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "CarLinko (user@example.com)"
    assert result2["data"][CONF_EMAIL] == "user@example.com"
    assert result2["data"][CONF_REGION] == "sea"


@pytest.mark.asyncio
async def test_config_flow_invalid_auth(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.carlinko.config_flow.ApiClient.login",
        new_callable=AsyncMock,
        side_effect=AuthError("login failed"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "bad",
                CONF_REGION: "sea",
            },
        )
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_reauth_success(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_REGION: "sea",
        },
        title="CarLinko (user@example.com)",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.carlinko.config_flow.ApiClient.login",
        new_callable=AsyncMock,
        return_value="token",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
                "unique_id": entry.unique_id,
            },
            data=entry.data,
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "new-secret"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"


@pytest.mark.asyncio
async def test_reauth_invalid_password(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_REGION: "sea",
        },
        title="CarLinko (user@example.com)",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.carlinko.config_flow.ApiClient.login",
        new_callable=AsyncMock,
        side_effect=AuthError("login failed"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
                "unique_id": entry.unique_id,
            },
            data=entry.data,
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "wrong"},
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_auth"
    assert entry.data[CONF_PASSWORD] == "old"


@pytest.mark.asyncio
async def test_entity_value_resolver_battery() -> None:
    store = MagicMock()
    store.get_cost_config.return_value = {
        "tariff": 1000,
        "petrol_price": 1,
        "petrol_kml": 12,
        "currency": {},
    }
    resolver = EntityValueResolver(store)
    battery = next(s for s in ENTITY_SPECS if s.key == "battery")
    assert resolver.resolve_value(battery, {"battery": 77}) == 77
