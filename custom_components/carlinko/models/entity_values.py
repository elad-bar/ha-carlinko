"""Resolve EntitySpec values from live vehicle state + cost config (HA-free)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol, runtime_checkable

from ..common.consts import CHARGE_STATE, HV_STATE
from .entity_specs import EntitySpec

DerivedResolver = Callable[[EntitySpec, dict], Any]

_SEAT_LEVELS = {0: "off", 1: "l1", 2: "l2", 3: "l3"}


@runtime_checkable
class _StoreCostView(Protocol):
    """Minimal store surface used for cost knobs (CarlinkoStore)."""

    def get_cost_config(self) -> dict[str, Any]:
        """Return persisted cost knobs."""
        ...


def get_path(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, (list, tuple)):
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def doors(state: dict) -> int:
    try:
        return int(state.get("doors") or 0)
    except (TypeError, ValueError):
        return 0


class EntityValueResolver:
    """Map EntitySpec → value using data_path / resolve / config_key."""

    def __init__(self, store: _StoreCostView):
        self.store = store
        self._resolvers: dict[str, DerivedResolver] = {
            "charge_power": self._charge_power,
            "charge_state": self._charge_state,
            "hv_state": self._hv_state,
            "energy_left": self._energy_left,
            "updated": self._updated,
            "seat_level": self._seat_level,
            "tyres_problem": self._tyres_problem,
            "door_any": self._door_any,
            "door_bit": self._door_bit,
            "lock_state": self._lock_state,
            "climate_mode": self._climate_mode,
            "windows_state": self._windows_state,
            "sunroof_state": self._sunroof_state,
            "liftgate_state": self._liftgate_state,
        }

    def resolve_value(self, spec: EntitySpec, state: dict) -> Any:
        if spec.resolve:
            resolver = self._resolvers.get(spec.resolve)
            return resolver(spec, state) if resolver else None
        if spec.config_key:
            cost = self.store.get_cost_config() or {}
            return cost.get(spec.config_key)
        path = spec.data_path
        if path is None:
            return None
        if path.startswith("config:"):
            cost = self.store.get_cost_config() or {}
            return cost.get(path.split(":", 1)[1])
        return get_path(state, path)

    @staticmethod
    def _charge_power(_spec: EntitySpec, state: dict) -> Any:
        chg = state.get("charging") or {}
        if not chg.get("active"):
            return 0
        rate = chg.get("rate_kw")
        return 0 if rate is None else rate

    @staticmethod
    def _charge_state(_spec: EntitySpec, state: dict) -> Any:
        cstate = (state.get("charging") or {}).get("state")
        return CHARGE_STATE.get(cstate, "") if cstate is not None else ""

    @staticmethod
    def _hv_state(_spec: EntitySpec, state: dict) -> Any:
        hv = state.get("hv_state")
        return HV_STATE.get(hv, "unknown") if hv is not None else ""

    @staticmethod
    def _energy_left(_spec: EntitySpec, state: dict) -> Any:
        battery = state.get("battery")
        cap = state.get("battery_kwh")
        if battery is None or not cap:
            return None
        return round(battery / 100.0 * cap, 2)

    @staticmethod
    def _updated(_spec: EntitySpec, state: dict) -> Any:
        ts = state.get("updated_ts")
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(float(ts), tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    @staticmethod
    def _seat_level(spec: EntitySpec, state: dict) -> Any:
        path = spec.data_path
        if not path:
            return None
        raw = get_path(state, path)
        if raw is None:
            return None
        try:
            level = int(raw)
        except (TypeError, ValueError):
            return None
        return _SEAT_LEVELS.get(level)

    @staticmethod
    def _tyres_problem(_spec: EntitySpec, state: dict) -> Any:
        return (state.get("tyre_status") or "") == "check_tyres"

    @staticmethod
    def _door_any(_spec: EntitySpec, state: dict) -> Any:
        return doors(state) != 0

    @staticmethod
    def _door_bit(spec: EntitySpec, state: dict) -> Any:
        return bool(doors(state) & (spec.door_bit or 0))

    @staticmethod
    def _lock_state(_spec: EntitySpec, state: dict) -> Any:
        return "UNLOCKED" if state.get("unlocked") else "LOCKED"

    @staticmethod
    def _climate_mode(_spec: EntitySpec, state: dict) -> Any:
        return "cool" if state.get("ac_on") else "off"

    @staticmethod
    def _windows_state(_spec: EntitySpec, state: dict) -> Any:
        return "open" if state.get("windows") else "closed"

    @staticmethod
    def _sunroof_state(_spec: EntitySpec, state: dict) -> Any:
        return "open" if state.get("sunroof") else "closed"

    @staticmethod
    def _liftgate_state(_spec: EntitySpec, state: dict) -> Any:
        return "open" if state.get("trunk") else "closed"
