"""Signed REST helpers for notices / maintain / firmware (HA-free)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

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
    response.status = 200
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
    response.status = 200
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
    assert "timestamp" in payload
    headers = client.session.post.call_args.kwargs["headers"]
    assert headers["version"] == "1.12.0"
    expected = client.sign({**payload})
    assert headers["signature"] == expected


@pytest.mark.asyncio
async def test_is_online_signs_id_not_query() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "data": True})
    assert await client.is_online("veh-99") is True
    args, kwargs = client.session.get.call_args
    assert args[0].endswith("/user/vehicle/isOnline/veh-99")
    assert "params" not in kwargs
    headers = kwargs["headers"]
    assert headers["version"] == "1.12.0"
    assert headers["signature"] == client.sign(
        {"id": "veh-99", "timestamp": headers["timestamp"]}
    )


@pytest.mark.asyncio
async def test_login_body_includes_timestamp_and_version() -> None:
    client = _api_client()
    client.store.set_token = MagicMock(return_value={})
    _mock_post(client, {"code": "0000", "data": "tok-new"})
    _mock_get(client, {"code": "0000", "data": 1_700_000_000_000})

    token = await client.login()
    assert token == "tok-new"
    body = json.loads(client.session.post.call_args.kwargs["data"])
    headers = client.session.post.call_args.kwargs["headers"]
    assert body["timestamp"] == headers["timestamp"]
    assert body["dateTime"] == body["timestamp"]
    assert headers["version"] == "1.12.0"
    assert "token" not in headers
    assert headers["signature"] == client.sign({**body})
    log = client.query_log_for_diagnostics()
    assert not any("login" in k for k in log["account"])
    assert not any("login" in k for bucket in log["vehicles"].values() for k in bucket)


@pytest.mark.asyncio
async def test_get_notice_unread_count_global_omits_vehicle_id() -> None:
    client = _api_client()
    _mock_get(
        client,
        {"code": "0000", "data": {"systemNoticeVo": {"count": 1}}},
    )
    data = await client.get_notice_unread_count()
    assert data["systemNoticeVo"]["count"] == 1
    kwargs = client.session.get.call_args.kwargs
    assert "params" not in kwargs


@pytest.mark.asyncio
async def test_get_notices_without_vehicle_id() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "total": 1, "data": [{"noticeId": "n1"}]})
    page = await client.get_notices(None, 2, page=1, size=20)
    assert page["total"] == 1
    params = client.session.get.call_args.kwargs["params"]
    assert "vehicleId" not in params
    assert params["type"] == "2"


@pytest.mark.asyncio
async def test_sync_server_time_sets_skew() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "data": 2_000_000_000_000})
    with patch(
        "custom_components.carlinko.managers.api_client.time.time",
        return_value=1_000_000.0,
    ):
        server = await client.sync_server_time()
        assert server == 2_000_000_000_000
        assert client._time_skew_ms == 2_000_000_000_000 - 1_000_000_000
        assert client.now_ms() == str(2_000_000_000_000)
    args, kwargs = client.session.get.call_args
    assert args[0].endswith("/pub/timestamp")
    headers = kwargs["headers"]
    assert "signature" not in headers
    assert "token" not in headers
    assert "version" not in headers


@pytest.mark.asyncio
async def test_get_ws_connect_normalizes_url() -> None:
    client = _api_client()
    _mock_get(
        client,
        {"code": "0000", "data": "http://wss-cqr-sea.hzhjcl.com:4002"},
    )
    url = await client.get_ws_connect("sn-abc")
    assert url == "ws://wss-cqr-sea.hzhjcl.com:4002/"
    assert client.session.get.call_args.args[0].endswith("/netty/getConnect/2/sn-abc")


@pytest.mark.asyncio
async def test_get_vehicle_state_signs_id() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "data": "7700abcd"})
    d = await client.get_vehicle_state("veh-1")
    assert d["data"] == "7700abcd"
    args, kwargs = client.session.get.call_args
    assert args[0].endswith("/user/vehicle/state/veh-1")
    headers = kwargs["headers"]
    assert headers["signature"] == client.sign(
        {"id": "veh-1", "timestamp": headers["timestamp"]}
    )


def test_meta_from_api_row_identity_only() -> None:
    from custom_components.carlinko.managers.api_client import meta_from_api_row

    row = {
        "vehicleId": "v1",
        "deviceId": "sn-1",
        "licenseNumber": "P",
        "model": "J5",
        "vin": "VIN1",
        "remoteControls": {"commandList": []},
    }
    meta = meta_from_api_row(row)
    assert meta["vehicle_id"] == "v1"
    assert meta["device_sn"] == "sn-1"
    assert "api_row" not in meta


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


@pytest.mark.asyncio
async def test_query_log_records_locate_not_remote_control() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(
        side_effect=lambda vid: {
            "v1": {"device_sn": "sn-1"},
            "v2": {"device_sn": "sn-2"},
        }.get(vid, {})
    )
    _mock_post(client, {"code": "0000", "msg": "ok", "data": {"lat": 1.0}})
    await client.device_locate(vehicle_id="v1")
    await client.send_control("740100", vehicle_id="v1")
    log = client.query_log_for_diagnostics()
    assert "POST /maps/deviceLocate" in log["vehicles"]["v1"]
    rec = log["vehicles"]["v1"]["POST /maps/deviceLocate"]
    assert rec["request"]["http_status"] == 200
    assert rec["request"]["cloud_code"] == "0000"
    assert rec["response"]["data"]["lat"] == 1.0
    assert not any("remoteControl" in k for k in log["vehicles"]["v1"])


@pytest.mark.asyncio
async def test_query_log_locate_is_per_vehicle() -> None:
    client = _api_client()
    client.store.get_vehicle_meta = MagicMock(
        side_effect=lambda vid: {
            "v1": {"device_sn": "sn-1"},
            "v2": {"device_sn": "sn-2"},
        }.get(vid, {})
    )
    _mock_post(client, {"code": "0000", "data": {"lat": 1.0}})
    await client.device_locate(vehicle_id="v1")
    _mock_post(client, {"code": "0000", "data": {"lat": 2.0}})
    await client.device_locate(vehicle_id="v2")
    log = client.query_log_for_diagnostics()
    assert (
        log["vehicles"]["v1"]["POST /maps/deviceLocate"]["response"]["data"]["lat"]
        == 1.0
    )
    assert (
        log["vehicles"]["v2"]["POST /maps/deviceLocate"]["response"]["data"]["lat"]
        == 2.0
    )
    one = client.query_log_for_diagnostics("v1")
    assert set(one["vehicles"]) == {"v1"}


@pytest.mark.asyncio
async def test_query_log_user_vehicle_is_account() -> None:
    client = _api_client()
    _mock_get(client, {"code": "0000", "data": [{"vehicleId": "v1"}]})
    await client.async_list_vehicles(force=True)
    log = client.query_log_for_diagnostics()
    assert "GET /user/vehicle" in log["account"]
    assert log["account"]["GET /user/vehicle"]["request"]["cloud_code"] == "0000"
