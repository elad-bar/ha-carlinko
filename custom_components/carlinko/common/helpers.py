"""Shared decode helpers: tyre conversion + vehicleControlConfig parsing."""

from __future__ import annotations

import json

from .consts import (
    DEFAULT_TPMS_SCALE,
    KPA_TO_PSI,
    TYRE_INVALID,
    TYRE_TEMP_OFFSET,
    TYRE_TEMP_SCALE,
)


def partial_id(value: str | None, keep: int = 4) -> str | None:
    """Redact an id for logs/diagnostics (last ``keep`` chars only)."""
    if not value:
        return None
    text = str(value)
    if len(text) <= keep:
        return "***"
    return f"***{text[-keep:]}"


def pressure(x, scale=None, unit=None):
    if x == TYRE_INVALID:
        return None
    scale = DEFAULT_TPMS_SCALE if scale is None else scale
    unit = unit or "psi"
    kpa = x * scale
    if unit == "bar":
        return round(kpa / 100.0, 2)
    if unit == "kpa":
        return round(kpa)
    return round(kpa * KPA_TO_PSI, 1)


def temp(x):
    return (
        None if x == TYRE_INVALID else round(x * TYRE_TEMP_SCALE + TYRE_TEMP_OFFSET, 1)
    )


def parse_control_cfg(raw):
    """Normalize vehicleControlConfig (object or JSON string) to a dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def flag(src, key):
    return bool(src.get(key)) if src else False


def flags(src, mapping):
    return {oid: flag(src, key) for oid, key in mapping}


def seat_max(ac, flag_key, list_key):
    if not ac.get(flag_key):
        return 0
    lst = ac.get(list_key)
    if not isinstance(lst, list):
        return 0
    return max((i + 1 for i, on in enumerate(lst[:3]) if on), default=0)
