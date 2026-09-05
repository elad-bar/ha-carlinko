"""Parse vehicle render URLs from /user/vehicle rows (HA-free)."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

IMAGE_ANGLES = ("front", "side", "top")
_ANGLE_KEYS = {
    "front": ("Front", "front"),
    "side": ("Side", "side"),
    "top": ("Top", "top"),
}


def _parse_vehicle_img_config(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    raw = row.get("vehicleImgConfig")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            _LOGGER.debug("vehicleImgConfig JSON parse failed")
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed
    return None


def image_urls_from_row(row: dict[str, Any] | None) -> dict[str, str]:
    """Return lowercase angle → CDN URL from ``vehicleImgConfig``."""
    cfg = _parse_vehicle_img_config(row)
    if not cfg:
        return {}
    out: dict[str, str] = {}
    for angle, keys in _ANGLE_KEYS.items():
        value = None
        for key in keys:
            if key in cfg and cfg.get(key) is not None:
                value = cfg.get(key)
                break
        if value is None:
            continue
        url = str(value).strip()
        if url:
            out[angle] = url
    return out


def front_image_url_from_row(row: dict[str, Any] | None) -> str | None:
    """Return the Front CDN URL from ``vehicleImgConfig``, or None."""
    return image_urls_from_row(row).get("front")


def angle_from_entity_key(key: str) -> str | None:
    """Map EntitySpec key ``vehicle_<angle>`` → angle, or None."""
    prefix = "vehicle_"
    if not key.startswith(prefix):
        return None
    angle = key[len(prefix) :]
    return angle if angle in IMAGE_ANGLES else None
