"""Tests for entry.data region validation (HA-free)."""

from __future__ import annotations

import pytest

from custom_components.carlinko.common.consts import CONF_REGION
from custom_components.carlinko.common.helpers import require_region_from_entry_data


def test_require_region_ok() -> None:
    assert require_region_from_entry_data({CONF_REGION: "sea"}) == "sea"


def test_require_region_missing() -> None:
    with pytest.raises(ValueError, match="missing required config data key=region"):
        require_region_from_entry_data({})


def test_require_region_invalid() -> None:
    with pytest.raises(ValueError, match="invalid region"):
        require_region_from_entry_data({CONF_REGION: "nope"})
