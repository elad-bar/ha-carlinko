"""Mount synthetic ``carlinko`` package for the engine CLI (import side effect).

Import this module before any ``from carlinko...`` so managers/models load
without executing the HA integration ``__init__``.
"""

from __future__ import annotations

import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_ROOT = os.path.join(_REPO, "custom_components", "carlinko")

if not (
    "carlinko" in sys.modules and getattr(sys.modules["carlinko"], "__path__", None)
):
    _pkg = types.ModuleType("carlinko")
    _pkg.__file__ = os.path.join(_ROOT, "__init__.py")
    _pkg.__path__ = [_ROOT]  # type: ignore[attr-defined]
    _pkg.__package__ = "carlinko"
    sys.modules["carlinko"] = _pkg
