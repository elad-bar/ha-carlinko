"""Spec-driven platform setup helpers (Dolphin-style factory)."""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..managers.coordinator import CarlinkoCoordinator
from ..models.entity_specs import EntitySpec, get_entity_specs
from .base_entity import CarlinkoEntity

_LOGGER = logging.getLogger(__name__)

EntityFactory = Callable[[CarlinkoCoordinator, EntitySpec, str], CarlinkoEntity]


def async_setup_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: CarlinkoCoordinator,
    platform: str,
    async_add_entities: AddEntitiesCallback,
    entity_factory: EntityFactory,
) -> Callable[[], None]:
    """Create entities for every vehicle × platform; return unsub for unload."""
    known: dict[tuple[str, str], CarlinkoEntity] = {}

    def _wanted() -> list[tuple[str, EntitySpec]]:
        out: list[tuple[str, EntitySpec]] = []
        vids = coordinator.vehicle_ids
        first_vid = vids[0] if vids else None
        for vid in vids:
            state = coordinator.vehicle_data(vid)
            caps = coordinator.caps_for(vid)
            for spec in get_entity_specs(platform=platform, state=state, caps=caps):
                # Account-level cost knobs: one set only (first vehicle device).
                if spec.config_key and vid != first_vid:
                    continue
                out.append((vid, spec))
        return out

    def _add_new(items: list[tuple[str, EntitySpec]]) -> None:
        to_add: list[CarlinkoEntity] = []
        for vid, spec in items:
            key = (vid, spec.key)
            if key in known:
                continue
            entity = entity_factory(coordinator, spec, vid)
            known[key] = entity
            to_add.append(entity)
        if to_add:
            keys = [entity.spec.key for entity in to_add]
            if len(keys) <= 12:
                _LOGGER.debug(f"adding {len(to_add)} entities on {platform}: {keys}")
            else:
                _LOGGER.debug(f"adding {len(to_add)} entities on {platform}")
            async_add_entities(to_add)

    _add_new(_wanted())

    @callback
    def _on_specs_changed(vehicle_id: str, added: set[str], removed: set[str]) -> None:
        if vehicle_id == "":
            _LOGGER.debug(f"reconciling entities after fleet change on {platform}")
            # Fleet membership changed: reconcile full wanted set.
            wanted = {(vid, s.key): s for vid, s in _wanted()}
            wanted_keys = set(wanted)
            known_keys = set(known)
            for key in known_keys - wanted_keys:
                entity = known.pop(key, None)
                if entity is not None and getattr(entity, "hass", None) is not None:
                    hass.async_create_task(entity.async_remove(force_remove=True))
            _add_new([(vid, wanted[(vid, k)]) for vid, k in wanted_keys - known_keys])
            return

        if removed:
            _LOGGER.debug(
                f"removing {len(removed)} entities on {platform} "
                f"for vehicle={vehicle_id}"
            )
        for key_name in list(removed):
            key = (vehicle_id, key_name)
            entity = known.pop(key, None)
            if entity is not None and getattr(entity, "hass", None) is not None:
                hass.async_create_task(entity.async_remove(force_remove=True))
        if added:
            wanted_map = {s.key: s for vid, s in _wanted() if vid == vehicle_id}
            _LOGGER.debug(
                f"capability change platform={platform} "
                f"vehicle={vehicle_id} +{len(added)} -{len(removed)}"
            )
            _add_new([(vehicle_id, wanted_map[k]) for k in added if k in wanted_map])

    unsub = coordinator.register_entity_listener(_on_specs_changed)
    entry.async_on_unload(unsub)
    return unsub
