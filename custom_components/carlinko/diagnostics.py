"""Diagnostics for CarLinko config entries and devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .common.consts import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from .common.helpers import partial_id
from .managers.coordinator import CarlinkoCoordinator

TO_REDACT = {CONF_PASSWORD, "token", "password", "sign_key"}


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1]


def _entry_summary(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "title": entry.title,
        "domain": entry.domain,
        "unique_id": entry.unique_id,
        "region": entry.data.get(CONF_REGION),
        "email_domain": _email_domain(entry.data.get(CONF_EMAIL)),
    }


def _vehicle_diagnostics(
    coordinator: CarlinkoCoordinator, vehicle_id: str
) -> dict[str, Any]:
    meta = coordinator.store.get_vehicle_meta(vehicle_id)
    rt = coordinator.vehicle_runtime(vehicle_id)
    return {
        "vehicle_id": partial_id(vehicle_id),
        "device_sn": partial_id(
            meta.get("device_sn") or (rt.device_sn if rt else None)
        ),
        "model": meta.get("model"),
        "plate": meta.get("plate"),
        "connected": bool(rt.connected) if rt else False,
        "last_update_ts": rt.last_update_ts if rt else 0.0,
        "caps_keys": sorted(coordinator.caps_for(vehicle_id).keys()),
        "spec_keys": sorted(coordinator.current_spec_keys(vehicle_id)),
    }


def _vehicle_id_from_device(device: DeviceEntry) -> str | None:
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return str(identifier)
    return None


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
            vehicles_out.append(_vehicle_diagnostics(coordinator, vid))

    payload = {
        "entry": _entry_summary(entry),
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


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a single vehicle device."""
    vehicle_id = _vehicle_id_from_device(device)
    if not vehicle_id:
        return {"error": "unknown_device"}

    coordinator: CarlinkoCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None or vehicle_id not in coordinator.vehicle_ids:
        return {
            "error": "unknown_device",
            "entry": _entry_summary(entry),
        }

    meta = coordinator.store.get_vehicle_meta(vehicle_id)
    store_vehicle = async_redact_data(dict(meta), TO_REDACT | {"vin"})

    return {
        "entry": _entry_summary(entry),
        "vehicle": _vehicle_diagnostics(coordinator, vehicle_id),
        "store_vehicle": store_vehicle,
        "data": async_redact_data(dict(entry.data), TO_REDACT),
    }
