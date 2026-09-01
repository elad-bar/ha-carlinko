"""CarLinko HA services (notices, maintain history, firmware check)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .common.consts import DOMAIN
from .managers.coordinator import CarlinkoCoordinator

_LOGGER = logging.getLogger(__name__)

_SERVICE_USERS = f"{DOMAIN}_service_users"

SERVICE_GET_NOTICES = "get_notices"
SERVICE_GET_MAINTAIN_HISTORY = "get_maintain_history"
SERVICE_GET_MAINTAIN_DETAILS = "get_maintain_details"
SERVICE_CHECK_FIRMWARE = "check_firmware"

ATTR_VEHICLE_ID = "vehicle_id"
ATTR_PAGE = "page"
ATTR_QUERY_KEY = "query_key"
ATTR_MAINTAIN_ID = "maintain_id"

_VEHICLE_SCHEMA = {
    vol.Required(ATTR_VEHICLE_ID): cv.string,
}

SERVICE_SCHEMAS: dict[str, vol.Schema] = {
    SERVICE_GET_NOTICES: vol.Schema(
        {
            vol.Optional(ATTR_VEHICLE_ID): cv.string,
            vol.Optional(ATTR_PAGE, default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
        }
    ),
    SERVICE_GET_MAINTAIN_HISTORY: vol.Schema(
        {
            **_VEHICLE_SCHEMA,
            vol.Optional(ATTR_QUERY_KEY, default=""): cv.string,
            vol.Optional(ATTR_PAGE, default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
        }
    ),
    SERVICE_GET_MAINTAIN_DETAILS: vol.Schema(
        {
            **_VEHICLE_SCHEMA,
            vol.Required(ATTR_MAINTAIN_ID): cv.string,
        }
    ),
    SERVICE_CHECK_FIRMWARE: vol.Schema({**_VEHICLE_SCHEMA}),
}


def _coordinator_for_vehicle(
    hass: HomeAssistant, vehicle_id: str
) -> CarlinkoCoordinator:
    vid = str(vehicle_id or "").strip()
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if (
            isinstance(coordinator, CarlinkoCoordinator)
            and vid in coordinator.vehicle_ids
        ):
            return coordinator
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="unknown_vehicle",
        translation_placeholders={"vehicle_id": vid or "—"},
    )


def _any_coordinator(hass: HomeAssistant) -> CarlinkoCoordinator:
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, CarlinkoCoordinator):
            return coordinator
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="cannot_connect",
    )


async def _async_handle_get_notices(call: ServiceCall) -> dict[str, Any]:
    vid = str(call.data.get(ATTR_VEHICLE_ID) or "").strip() or None
    if vid:
        coordinator = _coordinator_for_vehicle(call.hass, vid)
    else:
        coordinator = _any_coordinator(call.hass)
    return await coordinator.async_get_notices(
        vid, page=int(call.data.get(ATTR_PAGE) or 1)
    )


async def _async_handle_get_maintain_history(call: ServiceCall) -> dict[str, Any]:
    coordinator = _coordinator_for_vehicle(call.hass, call.data[ATTR_VEHICLE_ID])
    return await coordinator.async_get_maintain_history(
        call.data[ATTR_VEHICLE_ID],
        query_key=str(call.data.get(ATTR_QUERY_KEY) or ""),
        page=int(call.data.get(ATTR_PAGE) or 1),
    )


async def _async_handle_get_maintain_details(call: ServiceCall) -> dict[str, Any]:
    coordinator = _coordinator_for_vehicle(call.hass, call.data[ATTR_VEHICLE_ID])
    return await coordinator.async_get_maintain_details(
        call.data[ATTR_VEHICLE_ID], call.data[ATTR_MAINTAIN_ID]
    )


async def _async_handle_check_firmware(call: ServiceCall) -> dict[str, Any]:
    coordinator = _coordinator_for_vehicle(call.hass, call.data[ATTR_VEHICLE_ID])
    return await coordinator.async_check_firmware(call.data[ATTR_VEHICLE_ID])


_HANDLERS = {
    SERVICE_GET_NOTICES: _async_handle_get_notices,
    SERVICE_GET_MAINTAIN_HISTORY: _async_handle_get_maintain_history,
    SERVICE_GET_MAINTAIN_DETAILS: _async_handle_get_maintain_details,
    SERVICE_CHECK_FIRMWARE: _async_handle_check_firmware,
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services (refcount across config entries)."""
    users = int(hass.data.get(_SERVICE_USERS) or 0)
    if users == 0:
        for name, handler in _HANDLERS.items():
            hass.services.async_register(
                DOMAIN,
                name,
                handler,
                schema=SERVICE_SCHEMAS[name],
                supports_response=SupportsResponse.ONLY,
            )
        _LOGGER.debug("CarLinko services registered")
    hass.data[_SERVICE_USERS] = users + 1


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Remove domain services when the last loaded entry unloads."""
    users = int(hass.data.get(_SERVICE_USERS) or 0) - 1
    if users > 0:
        hass.data[_SERVICE_USERS] = users
        return
    hass.data[_SERVICE_USERS] = 0
    for name in _HANDLERS:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
    _LOGGER.debug("CarLinko services unregistered")
