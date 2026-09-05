"""Vehicle image URL parse + store cache + download-once ensure."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.carlinko.managers.api_client import meta_from_api_row
from custom_components.carlinko.managers.store import CarlinkoStore
from custom_components.carlinko.models.vehicle_images import (
    front_image_url_from_row,
    image_urls_from_row,
)


def test_image_urls_from_json_string() -> None:
    row = {
        "vehicleImgConfig": json.dumps(
            {
                "Front": "https://cdn.example/front.png",
                "Side": "https://cdn.example/side.png",
                "Top": "https://cdn.example/top.png",
            }
        )
    }
    urls = image_urls_from_row(row)
    assert urls == {
        "front": "https://cdn.example/front.png",
        "side": "https://cdn.example/side.png",
        "top": "https://cdn.example/top.png",
    }
    assert front_image_url_from_row(row) == "https://cdn.example/front.png"


def test_image_urls_from_dict() -> None:
    row = {"vehicleImgConfig": {"Front": "https://cdn.example/f.jpg"}}
    assert image_urls_from_row(row) == {"front": "https://cdn.example/f.jpg"}


def test_image_urls_missing_or_invalid() -> None:
    assert image_urls_from_row(None) == {}
    assert image_urls_from_row({}) == {}
    assert image_urls_from_row({"vehicleImgConfig": "{"}) == {}
    assert image_urls_from_row({"vehicleImgConfig": {"Side": "x"}}) == {"side": "x"}


def test_meta_from_api_row_includes_all_image_urls() -> None:
    row = {
        "vehicleId": "v1",
        "deviceId": "sn-1",
        "licenseNumber": "P",
        "model": "J5",
        "vin": "VIN1",
        "vehicleImgConfig": json.dumps(
            {
                "Front": "https://cdn.example/front.png",
                "Side": "https://cdn.example/side.png",
                "Top": "https://cdn.example/top.png",
            }
        ),
    }
    meta = meta_from_api_row(row)
    assert meta["front_image_url"] == "https://cdn.example/front.png"
    assert meta["side_image_url"] == "https://cdn.example/side.png"
    assert meta["top_image_url"] == "https://cdn.example/top.png"


def test_store_vehicle_image_per_angle_and_legacy_migration() -> None:
    path = tempfile.mktemp(suffix=".json")
    try:
        store = CarlinkoStore(path=path)
        # Legacy flat Front blob.
        store.data["vehicle_images"] = {
            "v1": {
                "url": "https://cdn.example/front.png",
                "content_type": "image/png",
                "data": base64.b64encode(b"PNGDATA").decode("ascii"),
                "updated": 50.0,
            }
        }
        store.save()
        front = store.get_vehicle_image("v1", angle="front")
        assert front["url"] == "https://cdn.example/front.png"
        assert base64.b64decode(front["data"]) == b"PNGDATA"

        store.set_vehicle_image(
            "v1",
            angle="side",
            url="https://cdn.example/side.png",
            content_type="image/png",
            data_b64=base64.b64encode(b"SIDE").decode("ascii"),
            updated=100.0,
        )
        side = store.get_vehicle_image("v1", angle="side")
        assert side["url"] == "https://cdn.example/side.png"
        assert base64.b64decode(side["data"]) == b"SIDE"
        # Front still present after side write (migrated + preserved).
        assert store.get_vehicle_image("v1", angle="front")["data"]
        # Fleet sync must not wipe image cache.
        store.set_vehicles(
            {"v1": {"device_sn": "s1", "plate": "P", "model": "J5", "vin": "V"}}
        )
        assert store.get_vehicle_image("v1", angle="side")["data"]
        store.clear_vehicle_images("v1")
        assert store.get_vehicle_image("v1", angle="front") == {}
        assert store.get_vehicle_image("v1", angle="side") == {}
    finally:
        if os.path.isfile(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_ensure_vehicle_images_skips_when_cached() -> None:
    from custom_components.carlinko.managers.coordinator import CarlinkoCoordinator

    coordinator = MagicMock(spec=CarlinkoCoordinator)
    coordinator.store = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "front_image_url": "https://cdn.example/front.png",
        "side_image_url": "https://cdn.example/side.png",
    }
    coordinator.store.get_vehicle_image.side_effect = lambda vid, angle="front": {
        "url": f"https://cdn.example/{angle}.png",
        "data": "YWJj",
        "content_type": "image/png",
    }
    coordinator.api = MagicMock()
    coordinator.api.session = MagicMock()
    coordinator._publish_data = MagicMock()

    await CarlinkoCoordinator._ensure_vehicle_images(coordinator, "v1")
    coordinator.api.session.get.assert_not_called()
    coordinator.store.set_vehicle_image.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_vehicle_images_downloads_missing_angles() -> None:
    from custom_components.carlinko.managers.coordinator import CarlinkoCoordinator

    coordinator = MagicMock(spec=CarlinkoCoordinator)
    coordinator.store = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "front_image_url": "https://cdn.example/front.png",
        "side_image_url": "https://cdn.example/side.png",
        "top_image_url": "https://cdn.example/top.png",
    }

    def _cached(vid, angle="front"):
        if angle == "front":
            return {
                "url": "https://cdn.example/front.png",
                "data": "YWJj",
            }
        return {}

    coordinator.store.get_vehicle_image.side_effect = _cached
    coordinator._publish_data = MagicMock()
    coordinator._cdn_log_host = CarlinkoCoordinator._cdn_log_host

    resp = AsyncMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=b"IMGBYTES")
    resp.headers = {"Content-Type": "image/png"}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    coordinator.api = MagicMock()
    coordinator.api.session = session

    await CarlinkoCoordinator._ensure_vehicle_images(coordinator, "v1")
    assert session.get.call_count == 2
    angles = {
        c.kwargs.get("angle")
        for c in coordinator.store.set_vehicle_image.call_args_list
    }
    assert angles == {"side", "top"}
    coordinator._publish_data.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_vehicle_images_redownloads_when_url_changes() -> None:
    from custom_components.carlinko.managers.coordinator import CarlinkoCoordinator

    coordinator = MagicMock(spec=CarlinkoCoordinator)
    coordinator.store = MagicMock()
    coordinator.store.get_vehicle_meta.return_value = {
        "front_image_url": "https://cdn.example/front-v2.png"
    }
    coordinator.store.get_vehicle_image.return_value = {
        "url": "https://cdn.example/front-v1.png",
        "data": "YWJj",
    }
    coordinator._publish_data = MagicMock()
    coordinator._cdn_log_host = CarlinkoCoordinator._cdn_log_host

    resp = AsyncMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=b"NEW")
    resp.headers = {"Content-Type": "image/jpeg"}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    coordinator.api = MagicMock()
    coordinator.api.session = session

    await CarlinkoCoordinator._ensure_vehicle_images(coordinator, "v1")
    session.get.assert_called_once()
    assert (
        coordinator.store.set_vehicle_image.call_args.kwargs["url"]
        == "https://cdn.example/front-v2.png"
    )
    assert coordinator.store.set_vehicle_image.call_args.kwargs["angle"] == "front"
