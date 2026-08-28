"""Diagnostics for CarLinko config entries and devices."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .common.consts import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, DOMAIN
from .common.helpers import partial_id
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import get_entity_specs
from .models.entity_values import EntityValueResolver

TO_REDACT = {CONF_PASSWORD, "token", "password", "sign_key"}
STATE_REDACT = TO_REDACT | {"vin"}


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _live_state(coordinator: CarlinkoCoordinator, vehicle_id: str) -> dict[str, Any]:
    """Parsed vehicle state (same source as entities), redacted for export."""
    raw = dict(coordinator.vehicle_data(vehicle_id))
    return async_redact_data(_json_safe(raw), STATE_REDACT)


def _entity_values(coordinator: CarlinkoCoordinator, vehicle_id: str) -> dict[str, Any]:
    """Resolved EntitySpec values for the current state (logical entity snapshot)."""
    state = coordinator.vehicle_data(vehicle_id)
    caps = coordinator.caps_for(vehicle_id)
    resolver = EntityValueResolver(coordinator.store)
    out: dict[str, Any] = {}
    for spec in get_entity_specs(state=state, caps=caps):
        out[spec.key] = {
            "platform": spec.platform,
            "value": _json_safe(resolver.resolve_value(spec, state)),
        }
    return out


def _registry_entities(
    hass: HomeAssistant, entry: ConfigEntry, vehicle_id: str
) -> list[dict[str, Any]]:
    """HA entity registry rows + live states for this vehicle device."""
    prefix = f"carlinko_{vehicle_id}_"
    registry = er.async_get(hass)
    rows: list[dict[str, Any]] = []
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not ent.unique_id or not ent.unique_id.startswith(prefix):
            continue
        st = hass.states.get(ent.entity_id)
        row: dict[str, Any] = {
            "entity_id": ent.entity_id,
            "unique_id": ent.unique_id,
            "platform": ent.platform,
            "disabled_by": ent.disabled_by,
            "state": st.state if st is not None else None,
        }
        if st is not None:
            row["attributes"] = _json_safe(dict(st.attributes))
        rows.append(row)
    rows.sort(key=lambda item: item["entity_id"])
    return rows


def _vehicle_diagnostics(
    coordinator: CarlinkoCoordinator,
    vehicle_id: str,
    *,
    hass: HomeAssistant | None = None,
    entry: ConfigEntry | None = None,
) -> dict[str, Any]:
    meta = coordinator.store.get_vehicle_meta(vehicle_id)
    rt = coordinator.vehicle_runtime(vehicle_id)
    payload: dict[str, Any] = {
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
        "live_state": _live_state(coordinator, vehicle_id),
        "entity_values": _entity_values(coordinator, vehicle_id),
    }
    if hass is not None and entry is not None:
        payload["entities"] = _registry_entities(hass, entry, vehicle_id)
    return payload


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
            vehicles_out.append(
                _vehicle_diagnostics(coordinator, vid, hass=hass, entry=entry)
            )

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
        "vehicle": _vehicle_diagnostics(
            coordinator, vehicle_id, hass=hass, entry=entry
        ),
        "store_vehicle": store_vehicle,
        "data": async_redact_data(dict(entry.data), TO_REDACT),
    }
