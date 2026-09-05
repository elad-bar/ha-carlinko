"""Seat capability parsing (HA-free)."""

from __future__ import annotations

from custom_components.carlinko.common.consts import SEAT_CAPS
from custom_components.carlinko.common.helpers import inherit_rear_seat_caps, seat_max
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


def test_seat_max_requires_flag_and_list() -> None:
    assert seat_max(_ac(RearHeater=False), "RearHeater", "RearHeaterList") == 0
    assert seat_max(_ac(RearHeater=True), "RearHeater", "RearHeaterList") == 3
    assert seat_max({"RearHeater": True}, "RearHeater", "RearHeaterList") == 0


def test_inherit_rear_from_driver_when_rear_flags_off() -> None:
    raw = {oid: seat_max(_ac(), f, l) for oid, f, l in SEAT_CAPS}
    assert raw["heatL"] == 3
    assert raw["heatLR"] == 0
    assert raw["ventLR"] == 0

    seats = inherit_rear_seat_caps(raw)
    assert seats["heatLR"] == 3
    assert seats["heatRR"] == 3
    assert seats["ventLR"] == 3
    assert seats["ventRR"] == 3


def test_inherit_preserves_explicit_rear_caps() -> None:
    seats = inherit_rear_seat_caps(
        {
            "heatL": 3,
            "ventL": 2,
            "heatLR": 1,
            "heatRR": 2,
            "ventLR": 1,
            "ventRR": 0,
        }
    )
    assert seats["heatLR"] == 1
    assert seats["heatRR"] == 2
    assert seats["ventLR"] == 1
    assert seats["ventRR"] == 2


def test_inherit_skips_when_driver_disabled() -> None:
    seats = inherit_rear_seat_caps(
        {"heatL": 0, "ventL": 0, "heatLR": 0, "heatRR": 0, "ventLR": 0, "ventRR": 0}
    )
    assert seats["heatLR"] == 0
    assert seats["ventRR"] == 0


def test_caps_from_vehicle_inherits_rear_seats() -> None:
    from unittest.mock import MagicMock

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
    assert caps["seats"]["heatLR"] == 3
    assert caps["seats"]["heatRR"] == 3
    assert caps["seats"]["ventLR"] == 3
    assert caps["seats"]["ventRR"] == 3
