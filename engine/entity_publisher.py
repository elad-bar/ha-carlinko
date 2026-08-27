"""Dev-only: resolve EntitySpecs → INFO logs on value change."""
from __future__ import annotations

import logging
from typing import Any, Callable

from protocol.config_adapter import ConfigAdapter
from protocol.entity_specs import ENTITY_SPECS, EntitySpec, get_entity_specs
from protocol.entity_values import EntityValueResolver

_LOGGER = logging.getLogger(__name__)


class EntityPublisher:
    """Filter specs, resolve via EntityValueResolver, log deltas on change."""

    def __init__(self, config: ConfigAdapter, get_caps: Callable[[], dict]):
        self.config = config
        self.get_caps = get_caps
        self._resolver = EntityValueResolver(config)
        self._last: dict[str, Any] = {}

    def publish(self, state: dict) -> None:
        try:
            caps = self.get_caps() or {}
        except Exception:
            caps = {}
        state = state or {}
        specs = get_entity_specs(state=state, caps=caps)
        active = set()
        for spec in specs:
            active.add(spec.key)
            if not spec.has_live_state():
                continue
            value = self.resolve_value(spec, state)
            if spec.key not in self._last or self._last[spec.key] != value:
                old = (
                    "—"
                    if spec.key not in self._last
                    else spec.format_value(self._last[spec.key])
                )
                _LOGGER.info(
                    "%s: %s → %s",
                    spec.name,
                    old,
                    spec.format_value(value),
                )
                self._last[spec.key] = value
        for key in list(self._last):
            if key not in active:
                del self._last[key]

    def log_command(self, key: str, action: str | None = None) -> None:
        spec = next((s for s in ENTITY_SPECS if s.key == key), None)
        if not spec:
            _LOGGER.info("command %s %s", key, action)
            return
        if action is None and spec.platform == "button":
            action = "press"
        _LOGGER.info("%s", spec.format_command(action))

    def resolve_value(self, spec: EntitySpec, state: dict) -> Any:
        return self._resolver.resolve_value(spec, state)
