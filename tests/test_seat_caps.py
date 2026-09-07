"""Seat capability parsing (HA-free)."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.carlinko.common.consts import SEAT_CAPS
from custom_components.carlinko.common.helpers import overlay_rear_seat_caps, seat_max
from custom_components.carlinko.managers.api_client import ApiClient


def _ac(**overrides):
    base = {
        "DriverHeater": True,
        "DriverVent": True,
        "AssistantHeater": True,
        "AssistantVent": True,
        "LeftHeaterList": [True, True, True],
        "LeftVentList": [True, True, True],
        "RightHeaterList": [True, True, True],
        "RightVentList": [True, True, True],
        "RearHeater": False,
        "RearVent": False,
        "RearHeaterList": [True, True, True],
        "RearVentList": [True, True, True],
    }
    base.update(overrides)
    return base


def test_seat_max_flag_false_hides_even_with_list() -> None:
    assert seat_max(_ac(RearHeater=False), "RearHeater", "RearHeaterList") == 0


def test_seat_max_flag_true_with_list() -> None:
    assert seat_max(_ac(RearHeater=True), "RearHeater", "RearHeaterList") == 3


def test_seat_max_missing_list_defaults_all_levels() -> None:
    assert seat_max({"RearHeater": True}, "RearHeater", "RearHeaterList") == 3


def test_seat_max_missing_flag_is_hidden() -> None:
    assert (
        seat_max({"RearHeaterList": [True, True, True]}, "RearHeater", "RearHeaterList")
        == 0
    )


def test_seat_max_partial_list() -> None:
    assert (
        seat_max(
            _ac(RearHeater=True, RearHeaterList=[True, True, False]),
            "RearHeater",
            "RearHeaterList",
        )
        == 2
    )


def test_seat_max_empty_list() -> None:
    assert (
        seat_max(
            _ac(RearHeater=True, RearHeaterList=[]), "RearHeater", "RearHeaterList"
        )
        == 0
    )


def test_raw_caps_do_not_inherit_rear_from_driver() -> None:
    raw = {oid: seat_max(_ac(), f, l) for oid, f, l in SEAT_CAPS}
    assert raw["heatL"] == 3
    assert raw["ventL"] == 3
    assert raw["heatLR"] == 0
    assert raw["heatRR"] == 0
    assert raw["ventLR"] == 0
    assert raw["ventRR"] == 0


def test_rear_heat_only() -> None:
    ac = _ac(RearHeater=True, RearVent=False)
    assert seat_max(ac, "RearHeater", "RearHeaterList") == 3
    assert seat_max(ac, "RearVent", "RearVentList") == 0


def test_rear_vent_only() -> None:
    ac = _ac(RearHeater=False, RearVent=True)
    assert seat_max(ac, "RearHeater", "RearHeaterList") == 0
    assert seat_max(ac, "RearVent", "RearVentList") == 3


def test_caps_from_vehicle_does_not_promote_rear() -> None:
    store = MagicMock()
    store.data = {}
    client = ApiClient("user@example.com", "secret", "sea", store, MagicMock())
    caps = client._caps_from_vehicle(
        {
            "licenseNumber": "X",
            "vehicleControlConfig": {"A/C": _ac()},
        }
    )
    assert caps["seats"]["heatL"] == 3
    assert caps["seats"]["heatLR"] == 0
    assert caps["seats"]["heatRR"] == 0
    assert caps["seats"]["ventLR"] == 0
    assert caps["seats"]["ventRR"] == 0


def test_overlay_auto_leaves_cloud_hidden() -> None:
    caps = overlay_rear_seat_caps(
        {"seats": {"heatLR": 0, "heatRR": 0, "ventLR": 0, "ventRR": 0, "heatL": 3}},
        "auto",
        "auto",
    )
    assert caps["seats"]["heatLR"] == 0
    assert caps["seats"]["heatL"] == 3


def test_overlay_on_shows_rear_when_cloud_hidden() -> None:
    caps = overlay_rear_seat_caps(
        {"seats": {"heatLR": 0, "heatRR": 0, "ventLR": 0, "ventRR": 0}},
        "on",
        "on",
    )
    assert caps["seats"]["heatLR"] == 3
    assert caps["seats"]["heatRR"] == 3
    assert caps["seats"]["ventLR"] == 3
    assert caps["seats"]["ventRR"] == 3


def test_overlay_on_keeps_cloud_max() -> None:
    caps = overlay_rear_seat_caps(
        {"seats": {"heatLR": 2, "heatRR": 2, "ventLR": 0, "ventRR": 0}},
        "on",
        "auto",
    )
    assert caps["seats"]["heatLR"] == 2
    assert caps["seats"]["ventLR"] == 0


def test_overlay_off_hides_even_when_cloud_true() -> None:
    caps = overlay_rear_seat_caps(
        {"seats": {"heatLR": 3, "heatRR": 3, "ventLR": 3, "ventRR": 3}},
        "off",
        "off",
    )
    assert caps["seats"]["heatLR"] == 0
    assert caps["seats"]["ventRR"] == 0
