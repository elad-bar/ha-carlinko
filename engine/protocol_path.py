"""Expose ``custom_components/carlinko/protocol`` as top-level ``protocol``.

Avoids importing ``custom_components.carlinko`` (Home Assistant) and avoids
putting that directory on ``sys.path`` (which would shadow stdlib ``select``).
"""
from __future__ import annotations

import os
import sys
import types


def ensure_protocol_package(repo_root: str) -> None:
    if "protocol" in sys.modules:
        return
    root = os.path.join(repo_root, "custom_components", "carlinko", "protocol")
    pkg = types.ModuleType("protocol")
    pkg.__file__ = os.path.join(root, "__init__.py")
    pkg.__path__ = [root]  # type: ignore[attr-defined]
    pkg.__package__ = "protocol"
    sys.modules["protocol"] = pkg
