"""Diagnostics for CarLinko config entries and devices."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .common.consts import CONF_PASSWORD, DOMAIN
from .managers.coordinator import CarlinkoCoordinator

TO_REDACT = {CONF_PASSWORD, "token", "password", "sign_key"}
STATE_REDACT = TO_REDACT | {"vin"}


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


def _redact_query_log(log: dict[str, Any]) -> dict[str, Any]:
    return async_redact_data(_json_safe(log), STATE_REDACT)


def _entry_block(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "title": entry.title,
        "domain": entry.domain,
        "unique_id": entry.unique_id,
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": _json_safe(dict(entry.options)),
    }


def _strip_api_row(meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(meta)
    out.pop("api_row", None)
    return out


def _store_block(
    coordinator: CarlinkoCoordinator, vehicle_id: str | None
) -> dict[str, Any]:
    raw = dict(coordinator.store.data)
    vehicles = raw.get("vehicles")
    if isinstance(vehicles, dict):
        cleaned = {
            str(vid): _strip_api_row(dict(meta) if isinstance(meta, dict) else {})
            for vid, meta in vehicles.items()
        }
        if vehicle_id:
            vid = str(vehicle_id)
            cleaned = {vid: cleaned[vid]} if vid in cleaned else {}
        raw["vehicles"] = cleaned
    return async_redact_data(_json_safe(raw), STATE_REDACT)


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


def _entities_block(
    hass: HomeAssistant | None,
    entry: ConfigEntry,
    vehicle_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if hass is None:
        return {vid: [] for vid in vehicle_ids}
    return {vid: _registry_entities(hass, entry, vid) for vid in vehicle_ids}


def _vehicle_details(
    coordinator: CarlinkoCoordinator, vehicle_id: str
) -> dict[str, Any]:
    rt = coordinator.vehicle_runtime(vehicle_id)
    details = dict(coordinator.vehicle_data(vehicle_id))
    details["connected"] = bool(rt.connected) if rt else False
    details["last_update_ts"] = rt.last_update_ts if rt else 0.0
    details["caps_keys"] = sorted(coordinator.caps_for(vehicle_id).keys())
    details["spec_keys"] = sorted(coordinator.current_spec_keys(vehicle_id))
    return async_redact_data(_json_safe(details), STATE_REDACT)


def _query_logs(
    coordinator: CarlinkoCoordinator, vehicle_id: str | None
) -> dict[str, Any]:
    api = getattr(coordinator, "api", None)
    getter = getattr(api, "query_log_for_diagnostics", None)
    if not callable(getter):
        return {"account": {}, "vehicles": {}}
    raw = getter(vehicle_id)
    if not isinstance(raw, dict):
        return {"account": {}, "vehicles": {}}
    return {
        "account": _redact_query_log(raw.get("account") or {}),
        "vehicles": {
            str(vid): _redact_query_log(bucket if isinstance(bucket, dict) else {})
            for vid, bucket in (raw.get("vehicles") or {}).items()
        },
    }


def _account_block(
    coordinator: CarlinkoCoordinator, logs: dict[str, Any]
) -> dict[str, Any]:
    api = getattr(coordinator, "api", None)
    token = getattr(api, "token", None) if api is not None else None
    skew = getattr(api, "time_skew_ms", None) if api is not None else None
    if skew is None:
        skew = getattr(api, "_time_skew_ms", 0) if api is not None else 0
    return {
        "details": {
            "token_present": bool(token),
            "skew_ms": int(skew or 0),
            "connected": bool(coordinator.connected),
            "vehicle_count": len(coordinator.vehicle_ids),
        },
        "api": logs.get("account") or {},
    }


def _vehicles_block(
    coordinator: CarlinkoCoordinator,
    vehicle_ids: list[str],
    logs: dict[str, Any],
) -> dict[str, Any]:
    per = logs.get("vehicles") or {}
    out: dict[str, Any] = {}
    for vid in vehicle_ids:
        out[vid] = {
            "details": _vehicle_details(coordinator, vid),
            "api": per.get(vid) or {},
        }
    return out


def _diagnostics_payload(
    hass: HomeAssistant | None,
    entry: ConfigEntry,
    coordinator: CarlinkoCoordinator,
    *,
    vehicle_id: str | None = None,
) -> dict[str, Any]:
    ids = [str(vehicle_id)] if vehicle_id else list(coordinator.vehicle_ids)
    logs = _query_logs(coordinator, vehicle_id)
    return {
        "entry": _entry_block(entry),
        "store": _store_block(coordinator, vehicle_id),
        "entities": _entities_block(hass, entry, ids),
        "account": _account_block(coordinator, logs),
        "vehicles": _vehicles_block(coordinator, ids, logs),
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
    if coordinator is None:
        return {"entry": _entry_block(entry)}
    return _diagnostics_payload(hass, entry, coordinator)


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
            "entry": _entry_block(entry),
        }

    return _diagnostics_payload(hass, entry, coordinator, vehicle_id=vehicle_id)
