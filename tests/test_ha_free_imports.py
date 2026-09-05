"""HA-free import boundary for models / managers used by engine."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

_REPO = Path(__file__).resolve().parents[1]
_ENGINE = _REPO / "engine"
_HA_FREE_MODULES = (
    "carlinko.models.entity_specs",
    "carlinko.models.entity_values",
    "carlinko.models.vehicle_state",
    "carlinko.models.vehicle_images",
    "carlinko.models.exceptions",
    "carlinko.managers.api_client",
    "carlinko.managers.ws_client",
    "carlinko.managers.store",
    "carlinko.common.consts",
)


def _mount_ha_free() -> None:
    """Same synthetic package mount as engine/entrypoint.py."""
    sys.path.insert(0, str(_ENGINE))
    # Drop any prior custom_components.carlinko / carlinko loads.
    for name in list(sys.modules):
        if name == "carlinko" or name.startswith("carlinko."):
            del sys.modules[name]
        if name == "ha_free_path":
            del sys.modules[name]
    import ha_free_path  # noqa: F401


def test_ha_free_modules_import_without_homeassistant() -> None:
    """models + HA-free managers must not import homeassistant at load time."""
    had_ha = "homeassistant" in sys.modules
    _mount_ha_free()
    # If HA was already imported by other tests, we still verify our modules
    # do not list homeassistant in their co_names / dependency chain via
    # module-level imports recorded after a clean mount of carlinko.*.
    before = {
        k for k in sys.modules if k == "homeassistant" or k.startswith("homeassistant.")
    }

    for mod_name in _HA_FREE_MODULES:
        mod = importlib.import_module(mod_name)
        assert mod is not None
        # Module file must live under custom_components/carlinko (mounted as carlinko).
        assert "custom_components" in (mod.__file__ or "").replace("\\", "/")

    after = {
        k for k in sys.modules if k == "homeassistant" or k.startswith("homeassistant.")
    }
    # Importing HA-free slice must not introduce new homeassistant modules.
    assert after == before or had_ha
    newly = after - before
    assert not newly, f"HA-free import pulled in: {newly}"


def test_platforms_use_common_entity_setup() -> None:
    """Platform modules wire through common.entity_setup.async_setup_entities."""
    platforms = (
        "sensor",
        "binary_sensor",
        "number",
        "lock",
        "climate",
        "cover",
        "button",
        "switch",
        "select",
        "image",
    )
    root = _REPO / "custom_components" / "carlinko"
    for name in platforms:
        text = (root / f"{name}.py").read_text(encoding="utf-8")
        assert "from .common.entity_setup import async_setup_entities" in text
        assert "async_setup_entities(" in text


@pytest.mark.parametrize("mod_name", _HA_FREE_MODULES)
def test_ha_free_module_source_has_no_homeassistant_import(mod_name: str) -> None:
    """Static check: HA-free modules must not import homeassistant."""
    import re

    rel = mod_name.removeprefix("carlinko.").replace(".", "/") + ".py"
    path = _REPO / "custom_components" / "carlinko" / rel
    text = path.read_text(encoding="utf-8")
    assert not re.search(
        r"^(?:from|import)\s+homeassistant\b", text, re.MULTILINE
    ), f"{path} imports homeassistant"
