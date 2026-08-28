"""Pytest configuration.

Loads ``pytest_homeassistant_custom_component.plugins`` on Unix (needs ``fcntl``).
On Windows, skip HA runtime test modules; CI (Linux) runs the full suite.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Files that need the HA pytest plugin (hass fixture / MockConfigEntry).
_HASS_TEST_FILES = frozenset(
    {
        "test_config_flow.py",
        "test_coordinator.py",
        "test_setup_unload.py",
    }
)

_HASS_RUNTIME_AVAILABLE = sys.platform != "win32"
try:
    import fcntl  # noqa: F401
except ImportError:
    _HASS_RUNTIME_AVAILABLE = False

if _HASS_RUNTIME_AVAILABLE:
    pytest_plugins = ("pytest_homeassistant_custom_component.plugins",)
else:
    pytest_plugins = ()


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    """Do not import HA integration test modules when the plugin cannot load."""
    if _HASS_RUNTIME_AVAILABLE:
        return False
    return collection_path.name in _HASS_TEST_FILES


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest):
    """Load custom_components/ when the HA plugin is available."""
    if not _HASS_RUNTIME_AVAILABLE:
        yield
        return
    request.getfixturevalue("enable_custom_integrations")
    yield
