"""Config flow and reauth tests for CarLinko."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.config_flow import CarlinkoConfigFlow
from custom_components.carlinko.common.consts import (
    CONF_AVAILABILITY_SECONDS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_STREAM_BACKSTOP,
    DOMAIN,
)
from custom_components.carlinko.models.entity_specs import ENTITY_SPECS
from custom_components.carlinko.models.entity_values import EntityValueResolver
from custom_components.carlinko.models.exceptions import AuthError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

_VEHICLE = {
    "vehicleId": "veh-1",
    "deviceSn": "sn-1",
    "licenseNumber": "ABC123",
    "model": "J5",
}


@pytest.mark.asyncio
async def test_config_flow_user_success(hass: HomeAssistant) -> None:
    with (
        patch(
            "custom_components.carlinko.config_flow.ApiClient.login",
            new_callable=AsyncMock,
            return_value="token",
        ),
        patch(
            "custom_components.carlinko.config_flow.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[_VEHICLE],
        ),
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
    assert result2["result"].unique_id == "user@example.com"


@pytest.mark.asyncio
async def test_config_flow_multi_vehicle_creates_one_entry(hass: HomeAssistant) -> None:
    vehicles = [
        {**_VEHICLE, "vehicleId": "veh-1"},
        {**_VEHICLE, "vehicleId": "veh-2", "licenseNumber": "XYZ999"},
    ]
    with (
        patch(
            "custom_components.carlinko.config_flow.ApiClient.login",
            new_callable=AsyncMock,
            return_value="token",
        ),
        patch(
            "custom_components.carlinko.config_flow.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=vehicles,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "multi@example.com",
                CONF_PASSWORD: "secret",
                CONF_REGION: "sea",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["result"].unique_id == "multi@example.com"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.asyncio
async def test_config_flow_no_vehicles(hass: HomeAssistant) -> None:
    with (
        patch(
            "custom_components.carlinko.config_flow.ApiClient.login",
            new_callable=AsyncMock,
            return_value="token",
        ),
        patch(
            "custom_components.carlinko.config_flow.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "empty@example.com",
                CONF_PASSWORD: "secret",
                CONF_REGION: "sea",
            },
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "no_vehicles"


@pytest.mark.asyncio
async def test_config_flow_already_configured(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "sea",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.carlinko.config_flow.ApiClient.login",
            new_callable=AsyncMock,
            return_value="token",
        ),
        patch(
            "custom_components.carlinko.config_flow.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[_VEHICLE],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "secret",
                CONF_REGION: "sea",
            },
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_config_flow_second_account_ok(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="one@example.com",
        data={
            CONF_EMAIL: "one@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "sea",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.carlinko.config_flow.ApiClient.login",
            new_callable=AsyncMock,
            return_value="token",
        ),
        patch(
            "custom_components.carlinko.config_flow.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[_VEHICLE],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "two@example.com",
                CONF_PASSWORD: "secret",
                CONF_REGION: "sea",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["result"].unique_id == "two@example.com"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


@pytest.mark.asyncio
async def test_config_flow_invalid_auth(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    with patch(
        "custom_components.carlinko.config_flow.ApiClient.login",
        new_callable=AsyncMock,
        side_effect=AuthError("login failed"),
    ):
        with caplog.at_level(logging.WARNING):
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
    assert any(
        r.name == "custom_components.carlinko.config_flow"
        and "config flow failed step=user error=invalid_auth" in r.message
        for r in caplog.records
    )


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
async def test_reauth_missing_region_aborts(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
        },
        title="CarLinko (user@example.com)",
    )
    entry.add_to_hass(hass)

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
        {CONF_PASSWORD: "new-secret"},
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "unknown"
    assert entry.data[CONF_PASSWORD] == "old"


def test_config_flow_has_no_reconfigure_step() -> None:
    assert not hasattr(CarlinkoConfigFlow, "async_step_reconfigure")


@pytest.mark.asyncio
async def test_options_flow(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "sea",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_STREAM_BACKSTOP: 30,
            CONF_AVAILABILITY_SECONDS: 3600,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_REGION not in entry.options
    assert entry.options[CONF_STREAM_BACKSTOP] == 30
    assert entry.options[CONF_AVAILABILITY_SECONDS] == 3600


@pytest.mark.asyncio
async def test_entity_value_resolver_battery() -> None:
    store = MagicMock()
    store.get_cost_config.return_value = {
        "tariff": 1000,
        "petrol_price": 1,
        "petrol_kml": 12,
    }
    resolver = EntityValueResolver(store)
    battery = next(s for s in ENTITY_SPECS if s.key == "battery")
    assert resolver.resolve_value(battery, {"battery": 77}) == 77
