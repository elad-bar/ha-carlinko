"""The CarLinko Home Assistant integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .managers.coordinator import CarlinkoCoordinator, async_create_coordinator
from .managers.store import CarlinkoStore, ha_storage_key
from .common.consts import DOMAIN, PLATFORMS as _PLATFORM_NAMES, STORAGE_VERSION

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
    coordinator = await async_create_coordinator(hass, entry)
    try:
        await coordinator.async_start()
    except ConfigEntryAuthFailed:
        await coordinator.async_stop()
        raise
    except Exception as err:
        await coordinator.async_stop()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        ) from err

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CarlinkoConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = entry.runtime_data
    await coordinator.async_stop()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: CarlinkoConfigEntry) -> None:
    """Reload when options/data change."""
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
