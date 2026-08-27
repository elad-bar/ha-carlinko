"""Integration setup/unload and WebSocket availability tests."""
from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
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
from homeassistant.helpers.storage import Store

_VEHICLE = {
    "vehicleId": "veh-1",
    "deviceSn": "sn-1",
    "licenseNumber": "AAA111",
    "model": "J5",
    "vin": "VIN1",
}


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
async def test_async_setup_and_unload_entry(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.carlinko.managers.api_client.ApiClient.login",
            new_callable=AsyncMock,
            return_value="tok",
        ),
        patch(
            "custom_components.carlinko.managers.api_client.ApiClient.async_list_vehicles",
            new_callable=AsyncMock,
            return_value=[_VEHICLE],
        ),
        patch(
            "custom_components.carlinko.managers.coordinator.CarlinkoCoordinator._start_ws"
        ),
        patch(
            "custom_components.carlinko.managers.coordinator.CarlinkoCoordinator._async_wait_for_stream",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.carlinko.managers.coordinator.CarlinkoCoordinator._async_refresh_device"
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator: CarlinkoCoordinator = entry.runtime_data
        assert coordinator.vehicle_ids == ["veh-1"]
        assert len(coordinator._entity_listeners) >= 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert coordinator._stop.is_set()
        assert coordinator._entity_listeners == []


@pytest.mark.asyncio
async def test_ws_disconnect_then_reconnect_restores_availability(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Disconnect clears availability; reconnect + fresh frame restores it."""
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {
        "vehicles": {
            "veh-1": {
                "vehicle_id": "veh-1",
                "device_sn": "sn-1",
                "plate": "AAA111",
                "model": "J5",
            }
        },
        "vehicle_id": "veh-1",
        "device_sn": "sn-1",
    }
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())
    rt = VehicleRuntime(
        vehicle_id="veh-1",
        device_sn="sn-1",
        meta=store.get_vehicle_meta("veh-1"),
        vehicle_state=VehicleState(),
        last_update_ts=time.time(),
        connected=True,
    )
    coordinator._vehicles["veh-1"] = rt
    coordinator._was_available["veh-1"] = True

    assert coordinator.is_available("veh-1") is True

    # Disconnect (same path as WsClient on_connected(False) / runner finally).
    with caplog.at_level(logging.INFO):
        rt.connected = False
        coordinator._log_availability_transition("veh-1")

    assert coordinator.is_available("veh-1") is False
    assert any("became unavailable" in r.message for r in caplog.records)

    # Reconnect successfully: stream live again within the availability window.
    rt.connected = True
    rt.last_update_ts = time.time()
    coordinator._log_availability_transition("veh-1")

    assert coordinator.is_available("veh-1") is True
    assert coordinator._was_available["veh-1"] is True


@pytest.mark.asyncio
async def test_ws_runner_generic_error_restarts_ws(hass: HomeAssistant) -> None:
    """Unexpected WS runner exit clears the task and calls _start_ws again."""
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {
        "vehicles": {
            "veh-1": {
                "vehicle_id": "veh-1",
                "device_sn": "sn-1",
                "plate": "AAA111",
                "model": "J5",
            }
        },
        "vehicle_id": "veh-1",
        "device_sn": "sn-1",
    }
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())
    rt = VehicleRuntime(
        vehicle_id="veh-1",
        device_sn="sn-1",
        meta=store.get_vehicle_meta("veh-1"),
        vehicle_state=VehicleState(),
        connected=True,
        last_update_ts=time.time(),
    )
    # Pretend a live background task so restart logic clears it.
    rt.ws_task = MagicMock()
    coordinator._vehicles["veh-1"] = rt

    class _CrashWs:
        async def run(self, stop) -> None:
            raise RuntimeError("socket died")

    with patch.object(coordinator, "_start_ws") as start_ws:
        await coordinator._ws_runner("veh-1", _CrashWs())
        start_ws.assert_called_once_with("veh-1")
        assert rt.ws_task is None


@pytest.mark.asyncio
async def test_ws_runner_auth_failure_starts_reauth(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {
        "token": "tok",
        "vehicles": {
            "veh-1": {
                "vehicle_id": "veh-1",
                "device_sn": "sn-1",
                "plate": "AAA111",
                "model": "J5",
            }
        },
        "vehicle_id": "veh-1",
        "device_sn": "sn-1",
    }
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())
    coordinator.api.token = "tok"
    rt = VehicleRuntime(
        vehicle_id="veh-1",
        device_sn="sn-1",
        meta=store.get_vehicle_meta("veh-1"),
        vehicle_state=VehicleState(),
    )
    coordinator._vehicles["veh-1"] = rt

    class _FailWs:
        async def run(self, stop) -> None:
            raise AuthError("ws auth failed")

    with patch.object(entry, "async_start_reauth") as start_reauth:
        await coordinator._ws_runner("veh-1", _FailWs())
        start_reauth.assert_called_once_with(hass)
        assert rt.connected is False
