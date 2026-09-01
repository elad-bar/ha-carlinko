"""Signed REST helpers for notices / maintain / firmware (HA-free)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.carlinko.managers.api_client import ApiClient


def _api_client() -> ApiClient:
    store = MagicMock()
    store.data = {"token": "tok"}
    client = ApiClient("user@example.com", "secret", "sea", store, MagicMock())
    client.token = "tok"
    client.sign_key = b"mYj3fzMpn77bir66"
    return client


def _mock_get(client: ApiClient, payload: dict) -> None:
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    client.session.get = MagicMock(return_value=MagicMock())
    client.session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    client.session.get.return_value.__aexit__ = AsyncMock(return_value=None)


@pytest.mark.asyncio
async def test_get_notice_unread_count_signs_vehicle_id() -> None:
    client = _api_client()
    _mock_get(
        client,
        {
            "code": "0000",
            "data": {
                "vehicleNoticeVo": {"count": 2},
                "controlNoticeVo": {"count": 1},
            },
        },
    )
    data = await client.get_notice_unread_count("veh-1")
    assert data["vehicleNoticeVo"]["count"] == 2
    kwargs = client.session.get.call_args.kwargs
    assert kwargs["params"]["vehicleId"] == "veh-1"
    assert "signature" in kwargs["headers"]


@pytest.mark.asyncio
async def test_get_higher_firmware_none_when_empty() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "data": None})
    assert await client.get_higher_firmware("sn-1", "1.0.0") is None


@pytest.mark.asyncio
async def test_get_maintain_details_signs_maintain_id() -> None:
    client = _api_client()
    _mock_get(
        client,
        {
            "code": "0000",
            "data": {"maintainProject": "Oil change", "logList": []},
        },
    )
    data = await client.get_maintain_details("mid-9")
    assert data["maintainProject"] == "Oil change"
    kwargs = client.session.get.call_args.kwargs
    assert kwargs["params"]["maintainId"] == "mid-9"
    assert client.session.get.call_args.args[0].endswith("/user/maintain/details/mid-9")


def _mock_post(client: ApiClient, payload: dict) -> None:
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    client.session.post = MagicMock(return_value=MagicMock())
    client.session.post.return_value.__aenter__ = AsyncMock(return_value=response)
    client.session.post.return_value.__aexit__ = AsyncMock(return_value=None)


@pytest.mark.asyncio
async def test_send_control_uses_per_vehicle_sn_only() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(
        side_effect=lambda vid: {
            "v1": {"device_sn": "sn-1"},
            "v2": {"device_sn": "sn-2"},
        }.get(vid, {})
    )
    client._veh_by_id = {
        "v1": {"vehicleId": "v1", "deviceId": "sn-1"},
        "v2": {"vehicleId": "v2", "deviceId": "sn-2"},
    }
    _mock_post(client, {"code": "0000"})

    await client.send_control("740100", vehicle_id="v2")
    body = client.session.post.call_args.kwargs["data"]
    payload = json.loads(body)
    assert payload["vehicleId"] == "v2"
    assert payload["deviceSn"] == "sn-2"


@pytest.mark.asyncio
async def test_send_control_missing_sn_skips() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(return_value={})
    client._veh_by_id = {}
    result = await client.send_control("740100", vehicle_id="missing")
    assert result["code"] == "-1"
    assert client.session.post.call_count == 0


@pytest.mark.asyncio
async def test_device_locate_requires_sn() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(return_value={})
    result = await client.device_locate(vehicle_id="v1")
    assert result["code"] == "-1"


def test_ids_for_never_borrows_other_car() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(
        side_effect=lambda vid: {"v1": {"device_sn": "sn-1"}}.get(vid, {})
    )
    client._veh_by_id = {"v1": {"vehicleId": "v1", "deviceId": "sn-1"}}
    assert client.ids_for("v2") == ("v2", "")
    assert client.ids_for("v1") == ("v1", "sn-1")


def test_control_caps_requires_vehicle_id() -> None:
    client = _api_client()
    client._caps_by_id = {"v1": {"Lock": True}, "v2": {"Lock": False}}
    assert client.control_caps("v2") == {"Lock": False}
    assert client.control_caps("") == {}
    assert client.control_caps("missing") == {}


def test_device_sn_of_reads_device_id() -> None:
    from custom_components.carlinko.managers.api_client import device_sn_of

    assert device_sn_of({"deviceId": "EME1263A27011284"}) == "EME1263A27011284"
    assert device_sn_of({"deviceSn": "ignored"}) == ""
    assert device_sn_of({}) == ""
