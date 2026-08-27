"""Diagnostics for CarLinko config entries."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from .coordinator import CarlinkoCoordinator

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
    coordinator: CarlinkoCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    vehicle = {}
    caps: dict[str, Any] = {}
    spec_keys: list[str] = []
    connected = False
    last_update_ts = 0.0
    vehicle_id = None
    device_sn = None

    if coordinator is not None:
        connected = coordinator.connected
        last_update_ts = coordinator.last_update_ts
        vehicle_id = coordinator.vehicle_id
        device_sn = coordinator.api.device_sn
        vehicle = dict(
            (coordinator.data or {}).get("vehicle")
            or coordinator.store.get_vehicle()
            or {}
        )
        caps = coordinator.caps
        spec_keys = sorted(coordinator.current_spec_keys())

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
            "vehicle_id": _partial_id(vehicle_id),
            "device_sn": _partial_id(device_sn),
            "model": vehicle.get("model"),
            "plate": vehicle.get("plate"),
            "spec_keys": spec_keys,
            "caps_keys": sorted(caps.keys()) if isinstance(caps, dict) else [],
        },
        "data": async_redact_data(dict(entry.data), TO_REDACT),
    }
    if coordinator is not None:
        store_data = dict(coordinator.store.data)
        payload["store"] = async_redact_data(store_data, TO_REDACT | {"vin"})
    return payload
