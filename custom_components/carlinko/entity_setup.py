"""Spec-driven platform setup helpers (Dolphin-style factory)."""
from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CarlinkoCoordinator
from .entity import CarlinkoEntity
from .protocol.entity_specs import EntitySpec, get_entity_specs

_LOGGER = logging.getLogger(__name__)


def async_setup_spec_platform(
    hass: HomeAssistant,
    coordinator: CarlinkoCoordinator,
    platform: str,
    async_add_entities: AddEntitiesCallback,
    entity_factory: Callable[[CarlinkoCoordinator, EntitySpec], CarlinkoEntity],
) -> None:
    """Create entities for ``platform`` and listen for caps-driven add/remove."""
    known: dict[str, CarlinkoEntity] = {}

    def _wanted() -> list[EntitySpec]:
        state = coordinator.data or coordinator.vehicle_state.data or {}
        return get_entity_specs(
            platform=platform, state=state, caps=coordinator.caps
        )

    def _add_new(specs: list[EntitySpec]) -> None:
        to_add: list[CarlinkoEntity] = []
        for spec in specs:
            if spec.key in known:
                continue
            entity = entity_factory(coordinator, spec)
            known[spec.key] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _add_new(_wanted())

    @callback
    def _on_specs_changed(added: set[str], removed: set[str]) -> None:
        for key in list(removed):
            entity = known.pop(key, None)
            if entity is not None and getattr(entity, "hass", None) is not None:
                hass.async_create_task(entity.async_remove(force_remove=True))
        if added:
            wanted = {s.key: s for s in _wanted()}
            _add_new([wanted[k] for k in added if k in wanted])

    coordinator.register_entity_listener(_on_specs_changed)
