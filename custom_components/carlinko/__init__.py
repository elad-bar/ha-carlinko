"""The CarLinko Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .common.consts import DOMAIN, PLATFORMS as _PLATFORM_NAMES, STORAGE_VERSION
from .common.helpers import partial_id
from .managers.coordinator import CarlinkoCoordinator, async_create_coordinator
from .managers.store import CarlinkoStore, ha_storage_key
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform(p) for p in _PLATFORM_NAMES]

type CarlinkoConfigEntry = ConfigEntry[CarlinkoCoordinator]

__all__ = [
    "DOMAIN",
    "PLATFORMS",
    "CarlinkoConfigEntry",
    "async_setup_entry",
    "async_unload_entry",
    "async_migrate_entry",
    "async_remove_entry",
]


async def async_setup_entry(hass: HomeAssistant, entry: CarlinkoConfigEntry) -> bool:
    """Set up CarLinko from a config entry."""
    suffix = (
        " (existing entry)" if getattr(entry, "runtime_data", None) is not None else ""
    )
    _LOGGER.info(f"setup entry entry_id={partial_id(entry.entry_id)}{suffix}")
    coordinator = await async_create_coordinator(hass, entry)
    try:
        await coordinator.async_start()
    except ConfigEntryAuthFailed:
        await coordinator.async_stop()
        _LOGGER.error(f"setup auth failed entry_id={partial_id(entry.entry_id)}")
        raise
    except Exception as err:
        await coordinator.async_stop()
        _LOGGER.exception("CarLinko setup failed")
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        ) from err

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    async_setup_services(hass)
    _LOGGER.debug(f"async_forward_entry_setups platforms={len(PLATFORMS)}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(f"platforms setup complete count={len(PLATFORMS)}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CarlinkoConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        f"unload entry entry_id={partial_id(entry.entry_id)} domains={len(PLATFORMS)}"
    )
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _LOGGER.info(f"unload platforms ok={unload_ok}")
    coordinator = entry.runtime_data
    await coordinator.async_stop()
    if unload_ok:
        async_unload_services(hass)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: CarlinkoConfigEntry) -> None:
    """Reload when options/data change."""
    _LOGGER.info(
        f"reload entry entry_id={partial_id(entry.entry_id)} reason=update_listener"
    )
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry versions (hub account entry; no data shape change yet)."""
    if entry.version > 1:
        return False
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete store so tokens do not linger after removal."""
    store = CarlinkoStore(
        hass,
        ha_store=Store(hass, STORAGE_VERSION, ha_storage_key(entry.entry_id)),
    )
    await store.async_remove()
    _LOGGER.info(f"remove entry entry_id={partial_id(entry.entry_id)} store deleted")
