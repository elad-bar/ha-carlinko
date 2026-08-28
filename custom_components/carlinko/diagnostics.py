"""Diagnostics for CarLinko config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .common.consts import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from .managers.coordinator import CarlinkoCoordinator

TO_REDACT = {CONF_PASSWORD, "token", "password", "sign_key"}


def _partial_id(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) <= keep:
        return "***"
    return f"***{text[-keep:]}"


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator: CarlinkoCoordinator | None = getattr(entry, "runtime_data", None)
    vehicles_out: list[dict[str, Any]] = []
    connected = False
    last_update_ts = 0.0
    spec_keys: list[str] = []

    if coordinator is not None:
        connected = coordinator.connected
        last_update_ts = coordinator.last_update_ts
        spec_keys = sorted(coordinator.current_spec_keys())
        for vid in coordinator.vehicle_ids:
            meta = coordinator.store.get_vehicle_meta(vid)
            rt = coordinator.vehicle_runtime(vid)
            vehicles_out.append(
                {
                    "vehicle_id": _partial_id(vid),
                    "device_sn": _partial_id(
                        meta.get("device_sn") or (rt.device_sn if rt else None)
                    ),
                    "model": meta.get("model"),
                    "plate": meta.get("plate"),
                    "connected": bool(rt.connected) if rt else False,
                    "last_update_ts": rt.last_update_ts if rt else 0.0,
                    "caps_keys": sorted(coordinator.caps_for(vid).keys()),
                }
            )

    payload = {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "unique_id": entry.unique_id,
            "region": entry.data.get(CONF_REGION),
            "email_domain": _email_domain(entry.data.get(CONF_EMAIL)),
        },
        "runtime": {
            "connected": connected,
            "last_update_ts": last_update_ts,
            "vehicle_count": len(vehicles_out),
            "vehicles": vehicles_out,
            "spec_keys": spec_keys,
        },
        "data": async_redact_data(dict(entry.data), TO_REDACT),
    }
    if coordinator is not None:
        store_data = dict(coordinator.store.data)
        payload["store"] = async_redact_data(store_data, TO_REDACT | {"vin"})
    return payload
