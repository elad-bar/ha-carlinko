"""Signed REST helpers for notices / maintain / firmware (HA-free)."""

from __future__ import annotations

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
