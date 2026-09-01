"""Coordinator auth-failure and multi-vehicle tests."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlinko.common.consts import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
    EVENT_NOTICE,
    STORAGE_VERSION,
)
from custom_components.carlinko.managers.coordinator import (
    CarlinkoCoordinator,
    VehicleRuntime,
)
from custom_components.carlinko.managers.store import CarlinkoStore, ha_storage_key
from custom_components.carlinko.models.exceptions import AuthError
from custom_components.carlinko.models.vehicle_state import VehicleState
from custom_components.carlinko.services import (
    SERVICE_GET_NOTICES,
    _coordinator_for_vehicle,
    async_setup_services,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store

_VEHICLES = [
    {
        "vehicleId": "veh-1",
        "deviceId": "sn-1",
        "licenseNumber": "AAA111",
        "model": "J5",
        "vin": "VIN1",
    },
    {
        "vehicleId": "veh-2",
        "deviceId": "sn-2",
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
        patch.object(
            coordinator.api,
            "device_locate",
            new_callable=AsyncMock,
            return_value={"code": "50052", "msg": "fail", "data": None},
        ),
        patch.object(
            coordinator.api,
            "get_higher_firmware",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(
            coordinator.api,
            "get_notice_unread_count",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch.object(
            coordinator.api,
            "get_notices",
            new_callable=AsyncMock,
            return_value={"total": 0, "data": []},
        ),
        patch.object(
            coordinator.api,
            "get_maintain_page",
            new_callable=AsyncMock,
            return_value={"total": 0, "data": []},
        ),
    ):
        await coordinator.async_start()
        await coordinator.async_stop()

    assert set(coordinator.vehicle_ids) == {"veh-1", "veh-2"}
    assert "veh-1" in store.get_vehicles()
    assert "veh-2" in store.get_vehicles()
    assert store.get_vehicles()["veh-1"]["plate"] == "AAA111"
    assert store.get_vehicles()["veh-2"]["plate"] == "BBB222"
    assert store.get_vehicles()["veh-1"].get("location_supported") is True


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
        patch.object(
            coordinator.api,
            "device_locate",
            new_callable=AsyncMock,
            return_value={"code": "50052", "msg": "fail", "data": None},
        ),
        patch.object(
            coordinator.api,
            "get_higher_firmware",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(
            coordinator.api,
            "get_notice_unread_count",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch.object(
            coordinator.api,
            "get_notices",
            new_callable=AsyncMock,
            return_value={"total": 0, "data": []},
        ),
        patch.object(
            coordinator.api,
            "get_maintain_page",
            new_callable=AsyncMock,
            return_value={"total": 0, "data": []},
        ),
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


@pytest.mark.asyncio
async def test_auth_failure_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())

    with (
        caplog.at_level(logging.WARNING),
        patch.object(entry, "async_start_reauth"),
    ):
        await coordinator._async_handle_auth_failure(AuthError("token dead"))

    assert any("auth failure source=" in r.message for r in caplog.records)
    assert any("starting reauth flow" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_notice_poll_bootstrap_then_dedup(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    store.data = {
        "vehicles": {
            "veh-1": {
                "vehicle_id": "veh-1",
                "device_sn": "sn-1",
                "plate": "AAA",
                "model": "J5",
            }
        }
    }
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())
    rt = VehicleRuntime(
        vehicle_id="veh-1",
        device_sn="sn-1",
        meta=store.get_vehicle_meta("veh-1"),
        vehicle_state=VehicleState(),
    )
    coordinator._vehicles["veh-1"] = rt
    coordinator._seed_rest_slices_from_meta("veh-1")

    events: list[dict] = []

    def _capture(event) -> None:
        events.append(dict(event.data))

    hass.bus.async_listen(EVENT_NOTICE, _capture)

    unread = {
        "vehicleNoticeVo": {"count": 1},
        "controlNoticeVo": {"count": 0},
    }
    page = {
        "total": 1,
        "data": [
            {
                "noticeId": "n1",
                "title": "Door open",
                "contents": "Driver door",
                "createdTime": "2026-01-01T00:00:00",
            }
        ],
    }

    with (
        patch.object(
            coordinator.api,
            "get_notice_unread_count",
            new_callable=AsyncMock,
            return_value=unread,
        ),
        patch.object(
            coordinator.api,
            "get_notices",
            new_callable=AsyncMock,
            return_value=page,
        ),
    ):
        await coordinator._poll_notices_vehicle("veh-1")
        await hass.async_block_till_done()
        assert events == []
        assert "n1" in store.get_vehicle_meta("veh-1").get("notice_seen_ids")

        await coordinator._poll_notices_vehicle("veh-1")
        await hass.async_block_till_done()
        assert events == []

        page2 = {
            "total": 2,
            "data": [
                {
                    "noticeId": "n2",
                    "title": "New alert",
                    "contents": "Body",
                    "createdTime": "2026-01-02T00:00:00",
                },
                page["data"][0],
            ],
        }
        coordinator.api.get_notice_unread_count = AsyncMock(
            return_value={
                "vehicleNoticeVo": {"count": 2},
                "controlNoticeVo": {"count": 0},
            }
        )
        coordinator.api.get_notices = AsyncMock(return_value=page2)
        await coordinator._poll_notices_vehicle("veh-1")
        await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0]["notice_id"] == "n2"
    assert events[0]["vehicle_id"] == "veh-1"
    assert rt.vehicle_state.data["notices"]["unread"] == 2


@pytest.mark.asyncio
async def test_service_rejects_unknown_vehicle(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    store = _store(hass, entry)
    coordinator = CarlinkoCoordinator(hass, entry, store, MagicMock())
    entry.runtime_data = coordinator
    coordinator._vehicles["veh-1"] = VehicleRuntime(
        vehicle_id="veh-1",
        device_sn="sn-1",
        meta={"vehicle_id": "veh-1", "device_sn": "sn-1"},
    )
    async_setup_services(hass)

    with pytest.raises(HomeAssistantError):
        _coordinator_for_vehicle(hass, "missing-veh")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NOTICES,
            {"vehicle_id": "missing-veh"},
            blocking=True,
            return_response=True,
        )
