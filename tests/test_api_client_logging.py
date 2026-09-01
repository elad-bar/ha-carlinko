"""ApiClient logging (HA-free)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.carlinko.managers.api_client import ApiClient


def _client() -> ApiClient:
    store = MagicMock()
    store.data = {}
    return ApiClient("user@example.com", "secret", "sea", store, MagicMock())


def test_index_vehicles_caps_parse_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client()
    row = {
        "vehicleId": "veh-long-id-1234",
        "deviceId": "sn-1",
        "vehicleControlConfig": "{}",
    }
    with (
        caplog.at_level(logging.WARNING),
        patch(
            "custom_components.carlinko.managers.api_client.flags",
            side_effect=ValueError("bad caps"),
        ),
    ):
        client._index_vehicles([row])

    assert client._caps_by_id.get("veh-long-id-1234") == {}
    assert any("vehicleControlConfig" in r.message for r in caplog.records)


def test_index_vehicles_no_global_ids() -> None:
    client = _client()
    client._index_vehicles(
        [
            {"vehicleId": "veh-1", "deviceId": "sn-1", "vehicleControlConfig": "{}"},
            {"vehicleId": "veh-2", "deviceId": "sn-2", "vehicleControlConfig": "{}"},
        ]
    )
    assert not hasattr(client, "vehicle_id")
    assert not hasattr(client, "device_sn")
    assert "veh-1" in client._veh_by_id
    assert "veh-2" in client._veh_by_id


@pytest.mark.asyncio
async def test_login_ok_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    client = _client()
    session = MagicMock()
    client.session = session
    response = MagicMock()
    response.json = AsyncMock(
        return_value={"code": "0000", "data": {"token": "tok-abc"}}
    )
    session.post = MagicMock(return_value=MagicMock())
    session.post.return_value.__aenter__ = AsyncMock(return_value=response)
    session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    client.store.set_token = MagicMock(return_value={})

    with caplog.at_level(logging.INFO):
        await client.login()

    assert any("login ok region=sea" in r.message for r in caplog.records)
