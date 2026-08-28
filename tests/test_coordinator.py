"""Coordinator auth-failure and multi-vehicle tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.common.consts import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
    STORAGE_VERSION,
)
from custom_components.carlinko.managers.coordinator import (
    CarlinkoCoordinator,
    VehicleRuntime,
)
from custom_components.carlinko.managers.store import CarlinkoStore, ha_storage_key
from custom_components.carlinko.models.exceptions import AuthError
from custom_components.carlinko.models.vehicle_state import VehicleState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store

_VEHICLES = [
    {
        "vehicleId": "veh-1",
        "deviceSn": "sn-1",
        "licenseNumber": "AAA111",
        "model": "J5",
        "vin": "VIN1",
    },
    {
        "vehicleId": "veh-2",
        "deviceSn": "sn-2",
        "licenseNumber": "BBB222",
        "model": "J7",
        "vin": "VIN2",
    },
]


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


def _store(hass: HomeAssistant, entry: MockConfigEntry) -> CarlinkoStore:
    return CarlinkoStore(
        hass,
        ha_store=Store(hass, STORAGE_VERSION, ha_storage_key(entry.entry_id)),
    )


@pytest.mark.asyncio
async def test_async_start_auth_error(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
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
async def test_async_start_multi_vehicle(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {}
    session = MagicMock()
    coordinator = CarlinkoCoordinator(hass, entry, store, session)

    with (
        patch.object(
            coordinator.api, "login", new_callable=AsyncMock, return_value="tok"
        ),
        patch.object(
            coordinator.api,
            "async_list_vehicles",
            new_callable=AsyncMock,
            return_value=_VEHICLES,
        ),
        patch.object(coordinator, "_start_ws"),
        patch.object(coordinator, "_async_wait_for_stream", new_callable=AsyncMock),
    ):
        await coordinator.async_start()
        await coordinator.async_stop()

    assert set(coordinator.vehicle_ids) == {"veh-1", "veh-2"}
    assert "veh-1" in store.get_vehicles()
    assert "veh-2" in store.get_vehicles()
    assert store.get_vehicles()["veh-1"]["plate"] == "AAA111"
    assert store.get_vehicles()["veh-2"]["plate"] == "BBB222"


@pytest.mark.asyncio
async def test_vehicle_list_add_remove(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {}
    session = MagicMock()
    coordinator = CarlinkoCoordinator(hass, entry, store, session)

    with (
        patch.object(
            coordinator.api, "login", new_callable=AsyncMock, return_value="tok"
        ),
        patch.object(
            coordinator.api,
            "async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[_VEHICLES[0]],
        ),
        patch.object(coordinator, "_start_ws"),
        patch.object(coordinator, "_stop_ws"),
        patch.object(coordinator, "_async_wait_for_stream", new_callable=AsyncMock),
    ):
        await coordinator.async_start()
        assert coordinator.vehicle_ids == ["veh-1"]

        events: list[tuple[str, set[str], set[str]]] = []

        def _listen(vid: str, added: set[str], removed: set[str]) -> None:
            events.append((vid, added, removed))

        coordinator.register_entity_listener(_listen)
        coordinator._sync_vehicles_from_rows(_VEHICLES)
        assert set(coordinator.vehicle_ids) == {"veh-1", "veh-2"}
        assert any(e[0] == "veh-2" for e in events)

        coordinator._sync_vehicles_from_rows([_VEHICLES[1]])
        assert coordinator.vehicle_ids == ["veh-2"]
        assert any(e[0] == "veh-1" and e[2] for e in events)

        await coordinator.async_stop()


@pytest.mark.asyncio
async def test_async_send_control_auth_error(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {
        "token": "dead",
        "vehicles": {
            "v1": {"vehicle_id": "v1", "device_sn": "s1", "plate": "P", "model": "M"}
        },
        "vehicle_id": "v1",
        "device_sn": "s1",
    }
    session = MagicMock()
    coordinator = CarlinkoCoordinator(hass, entry, store, session)
    coordinator.api.token = "dead"

    coordinator._vehicles["v1"] = VehicleRuntime(
        vehicle_id="v1",
        device_sn="s1",
        meta=store.get_vehicle_meta("v1"),
        vehicle_state=VehicleState(),
    )

    with (
        patch.object(
            coordinator.api, "send_control", new_callable=AsyncMock
        ) as send_control,
        patch.object(entry, "async_start_reauth") as start_reauth,
    ):
        send_control.side_effect = AuthError("relogin failed")
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator.async_send_control("740100", vehicle_id="v1")
        start_reauth.assert_called_once_with(hass)
