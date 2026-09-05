"""Shared decode helpers: tyre conversion + vehicleControlConfig parsing."""

from __future__ import annotations

import json
from typing import Any

from .consts import (
    CONF_REGION,
    DEFAULT_TPMS_SCALE,
    KNOWN_REGIONS,
    KPA_TO_PSI,
    LOCATION_UNSUPPORTED_CODES,
    OK_CODE,
    TYRE_INVALID,
    TYRE_TEMP_OFFSET,
    TYRE_TEMP_SCALE,
)


def require_region_from_entry_data(data: dict[str, Any]) -> str:
    """Return validated region from config entry data; raise ValueError if missing/invalid."""
    raw = data.get(CONF_REGION)
    if raw is None or not str(raw).strip():
        raise ValueError("missing required config data key=region")
    region = str(raw).strip()
    if region not in KNOWN_REGIONS:
        raise ValueError(f"invalid region={region!r}")
    return region


def partial_id(value: str | None, keep: int = 4) -> str | None:
    """Redact an id for logs/diagnostics (last ``keep`` chars only)."""
    if not value:
        return None
    text = str(value)
    if len(text) <= keep:
        return "***"
    return f"***{text[-keep:]}"


def mask_email(email: str | None) -> str:
    """Redact email for logs (first character + domain)."""
    if not email:
        return "***"
    text = str(email).strip()
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


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


def inherit_rear_seat_caps(seats: dict) -> dict:
    """Fill rear heat/vent caps from driver when cloud rear flags are off.

    Some cars expose rear seat UI in the app and ship ``RearHeaterList`` /
    ``RearVentList`` while ``RearHeater`` / ``RearVent`` stay false. Until the
    original app mapping is confirmed, mirror driver levels onto rear L/R when
    those rear caps are still zero.
    """
    out = dict(seats or {})
    heat_l = int(out.get("heatL") or 0)
    vent_l = int(out.get("ventL") or 0)
    if heat_l > 0:
        if int(out.get("heatLR") or 0) <= 0:
            out["heatLR"] = heat_l
        if int(out.get("heatRR") or 0) <= 0:
            out["heatRR"] = heat_l
    if vent_l > 0:
        if int(out.get("ventLR") or 0) <= 0:
            out["ventLR"] = vent_l
        if int(out.get("ventRR") or 0) <= 0:
            out["ventRR"] = vent_l
    return out


def interpret_device_locate_code(code: str | None) -> bool | None:
    """Map /maps/deviceLocate response code → location_supported.

    ``True`` = feature usable (entity may be unavailable until a fix).
    ``False`` = unsupported (do not create entity).
    ``None`` = unknown / leave prior (transport or unexpected code).
    """
    c = str(code or "").strip()
    if not c or c in ("-1",):
        return None
    if c in LOCATION_UNSUPPORTED_CODES:
        return False
    if c in (OK_CODE, "0"):
        return True
    # Business errors such as 50052 (query failed) still mean the maps API
    # accepted the SN — treat as supported, no coordinates yet.
    if c.isdigit() and len(c) == 5 and c.startswith("5"):
        return True
    return None
