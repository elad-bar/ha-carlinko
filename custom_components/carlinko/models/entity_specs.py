"""HA-agnostic entity catalog (Dolphin-style). No homeassistant imports.

Later these map to EntityDescription subclasses. EntityPublisher logs value
deltas (and commands) using format_value / format_command.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Callable


@dataclass(frozen=True, kw_only=True)
class EntitySpec:
    key: str
    platform: str
    name: str
    data_path: str | None = None  # dotted VehicleState path or "config:tariff"
    resolve: str | None = None  # named derived resolver (see EntityPublisher)
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    options: tuple[str, ...] | None = None
    when: str | None = None  # None | phev | direct_tpms | cap:...
    config_key: str | None = None  # tariff | petrol_price | petrol_kml
    commands: Mapping[str, str] = field(
        default_factory=dict
    )  # action → remoteControl hex
    door_bit: int | None = None  # for resolve="door_bit"

    def __post_init__(self) -> None:
        if isinstance(self.commands, dict):
            object.__setattr__(self, "commands", MappingProxyType(self.commands))

    def _command_map(self) -> dict[str, str]:
        return {k.lower(): v for k, v in self.commands.items()}

    def resolve_opcode(self, action: str) -> str | None:
        if not action or not self.commands:
            return None
        key = action.lower()
        mapped = self._command_map().get(key)
        if mapped:
            return mapped
        # State / HA aliases
        if self.key == "climate" and key == "cool":
            return self._command_map().get("on")
        if self.key == "lock":
            if key == "locked":
                return self._command_map().get("lock")
            if key == "unlocked":
                return self._command_map().get("unlock")
        return None

    def has_live_state(self) -> bool:
        """True if publish() can resolve a telemetry/config value for this spec."""
        return bool(self.data_path or self.resolve or self.config_key)

    def format_value(self, value: Any) -> str:
        if value is None:
            return "unknown"
        if self.unit == "%":
            return f"{value}%"
        if self.unit:
            return f"{value} {self.unit}"
        return str(value)

    def format_command(self, action: str | None = None) -> str:
        if self.config_key:
            return f"{self.name} config:{self.config_key}"
        act = action or ("press" if self.platform == "button" else None)
        if act is None:
            return self.name
        hex_code = self.resolve_opcode(act)
        if hex_code:
            return f"{self.name} → {act} ({hex_code})"
        return f"{self.name} → {act}"


ENTITY_SPECS: tuple[EntitySpec, ...] = (
    # --- sensors (always) ---
    EntitySpec(
        key="battery",
        platform="sensor",
        name="Battery",
        data_path="battery",
        unit="%",
        device_class="battery",
        state_class="measurement",
    ),
    EntitySpec(
        key="range",
        platform="sensor",
        name="Range",
        data_path="range",
        unit="km",
        device_class="distance",
        icon="mdi:map-marker-distance",
        state_class="measurement",
    ),
    EntitySpec(
        key="odometer",
        platform="sensor",
        name="Odometer",
        data_path="odo",
        unit="km",
        device_class="distance",
        icon="mdi:counter",
        state_class="total_increasing",
    ),
    EntitySpec(
        key="volt12",
        platform="sensor",
        name="12V Battery",
        data_path="volt12_calculated",
        unit="V",
        device_class="voltage",
        state_class="measurement",
    ),
    EntitySpec(
        key="volt12_status",
        platform="sensor",
        name="12V status",
        data_path="volt12_status",
        device_class="enum",
        options=("ok", "low", "critical"),
    ),
    EntitySpec(
        key="charge_power",
        platform="sensor",
        name="Charge Power",
        resolve="charge_power",
        unit="kW",
        device_class="power",
        state_class="measurement",
    ),
    EntitySpec(
        key="consumption",
        platform="sensor",
        name="Consumption",
        data_path="consumption_calculated",
        unit="kWh/100km",
        icon="mdi:lightning-bolt",
        state_class="measurement",
    ),
    EntitySpec(
        key="charge_remaining",
        platform="sensor",
        name="Charge remaining",
        data_path="charging.remaining_min",
        unit="min",
        device_class="duration",
        state_class="measurement",
    ),
    EntitySpec(
        key="charge_mode",
        platform="sensor",
        name="Charge mode",
        data_path="charging.mode",
        device_class="enum",
        options=("none", "ac", "dc"),
        icon="mdi:ev-plug-type2",
    ),
    EntitySpec(
        key="charge_state",
        platform="sensor",
        name="Charge state",
        resolve="charge_state",
        device_class="enum",
        options=("idle", "charging", "complete", "canceled", "hot", "stop"),
    ),
    EntitySpec(
        key="updated",
        platform="sensor",
        name="Updated",
        resolve="updated",
        device_class="timestamp",
    ),
    EntitySpec(
        key="hv_state",
        platform="sensor",
        name="HV state",
        resolve="hv_state",
        device_class="enum",
        options=("off", "lv", "ready", "unknown"),
        icon="mdi:car-electric",
    ),
    EntitySpec(
        key="wltc_range",
        platform="sensor",
        name="Rated range",
        data_path="wltc_range",
        unit="km",
        device_class="distance",
        icon="mdi:map-marker-distance",
        state_class="measurement",
    ),
    EntitySpec(
        key="energy_left",
        platform="sensor",
        name="Energy left",
        resolve="energy_left",
        unit="kWh",
        device_class="energy_storage",
        state_class="measurement",
    ),
    EntitySpec(
        key="tyre_status",
        platform="sensor",
        name="Tyre status",
        data_path="tyre_status",
        device_class="enum",
        options=("normal", "check_tyres"),
        icon="mdi:car-tire-alert",
    ),
    # --- binary sensors (always) ---
    EntitySpec(
        key="charging",
        platform="binary_sensor",
        name="Charging",
        data_path="charging.active",
        device_class="battery_charging",
    ),
    EntitySpec(
        key="online",
        platform="binary_sensor",
        name="Online",
        data_path="online",
        device_class="connectivity",
    ),
    EntitySpec(
        key="moving",
        platform="binary_sensor",
        name="Moving",
        data_path="moving",
        device_class="moving",
    ),
    EntitySpec(
        key="tyres_ok",
        platform="binary_sensor",
        name="Tyre problem",
        resolve="tyres_problem",
        device_class="problem",
    ),
    EntitySpec(
        key="door",
        platform="binary_sensor",
        name="Any door",
        resolve="door_any",
        device_class="door",
    ),
    EntitySpec(
        key="door_driver",
        platform="binary_sensor",
        name="Driver door",
        resolve="door_bit",
        door_bit=1,
        device_class="door",
    ),
    EntitySpec(
        key="door_passenger",
        platform="binary_sensor",
        name="Passenger door",
        resolve="door_bit",
        door_bit=2,
        device_class="door",
    ),
    EntitySpec(
        key="door_rear_left",
        platform="binary_sensor",
        name="Rear left door",
        resolve="door_bit",
        door_bit=4,
        device_class="door",
    ),
    EntitySpec(
        key="door_rear_right",
        platform="binary_sensor",
        name="Rear right door",
        resolve="door_bit",
        door_bit=8,
        device_class="door",
    ),
    EntitySpec(
        key="seat_heat_left",
        platform="binary_sensor",
        name="Seat heat left",
        data_path="seat_heat_l",
        device_class="heat",
    ),
    EntitySpec(
        key="seat_heat_right",
        platform="binary_sensor",
        name="Seat heat right",
        data_path="seat_heat_r",
        device_class="heat",
    ),
    EntitySpec(
        key="seat_vent_left",
        platform="binary_sensor",
        name="Seat vent left",
        data_path="seat_vent_l",
        icon="mdi:car-seat",
    ),
    EntitySpec(
        key="seat_vent_right",
        platform="binary_sensor",
        name="Seat vent right",
        data_path="seat_vent_r",
        icon="mdi:car-seat",
    ),
    EntitySpec(
        key="defrost",
        platform="binary_sensor",
        name="Defrost",
        data_path="defrost_front",
        icon="mdi:car-defrost-front",
    ),
    # --- PHEV ---
    EntitySpec(
        key="fuel",
        platform="sensor",
        name="Fuel",
        data_path="fuel.pct",
        unit="%",
        icon="mdi:gas-station",
        state_class="measurement",
        when="phev",
    ),
    EntitySpec(
        key="fuel_range",
        platform="sensor",
        name="Fuel range",
        data_path="fuel.range_km",
        unit="km",
        device_class="distance",
        icon="mdi:map-marker-distance",
        state_class="measurement",
        when="phev",
    ),
    EntitySpec(
        key="total_range",
        platform="sensor",
        name="Total range",
        data_path="fuel.total_range_km",
        unit="km",
        device_class="distance",
        icon="mdi:map-marker-distance",
        state_class="measurement",
        when="phev",
    ),
    EntitySpec(
        key="fuel_consumption",
        platform="sensor",
        name="Fuel consumption",
        data_path="fuel.l_100",
        unit="L/100km",
        icon="mdi:fuel",
        state_class="measurement",
        when="phev",
    ),
    # --- direct TPMS ---
    EntitySpec(
        key="tyre_fl",
        platform="sensor",
        name="Front left",
        data_path="tpms.0.psi",
        unit="psi",
        device_class="pressure",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_fl_temp",
        platform="sensor",
        name="Front left temp",
        data_path="tpms.0.temp",
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_fr",
        platform="sensor",
        name="Front right",
        data_path="tpms.1.psi",
        unit="psi",
        device_class="pressure",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_fr_temp",
        platform="sensor",
        name="Front right temp",
        data_path="tpms.1.temp",
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_rl",
        platform="sensor",
        name="Rear left",
        data_path="tpms.2.psi",
        unit="psi",
        device_class="pressure",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_rl_temp",
        platform="sensor",
        name="Rear left temp",
        data_path="tpms.2.temp",
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_rr",
        platform="sensor",
        name="Rear right",
        data_path="tpms.3.psi",
        unit="psi",
        device_class="pressure",
        state_class="measurement",
        when="direct_tpms",
    ),
    EntitySpec(
        key="tyre_rr_temp",
        platform="sensor",
        name="Rear right temp",
        data_path="tpms.3.temp",
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        when="direct_tpms",
    ),
    # --- config numbers ---
    EntitySpec(
        key="tariff",
        platform="number",
        name="Charging tariff",
        data_path="config:tariff",
        icon="mdi:currency-usd",
        config_key="tariff",
    ),
    EntitySpec(
        key="petrol_price",
        platform="number",
        name="Petrol price",
        data_path="config:petrol_price",
        icon="mdi:gas-station",
        config_key="petrol_price",
    ),
    EntitySpec(
        key="petrol_kml",
        platform="number",
        name="Petrol economy",
        data_path="config:petrol_kml",
        unit="km/L",
        icon="mdi:car-speed-limiter",
        config_key="petrol_kml",
    ),
    # --- body / climate state (commands gated by caps) ---
    EntitySpec(
        key="lock",
        platform="lock",
        name="Lock",
        resolve="lock_state",
        when="cap:lock",
        commands={
            "lock": "740100",
            "unlock": "740200",
            "locked": "740100",
            "unlocked": "740200",
        },
    ),
    EntitySpec(
        key="climate",
        platform="climate",
        name="Climate",
        resolve="climate_mode",
        when="cap:ac.switch",
        commands={"on": "741001", "off": "741000", "cool": "741001"},
    ),
    EntitySpec(
        key="windows",
        platform="cover",
        name="Windows",
        resolve="windows_state",
        when="cap:windows",
        commands={"open": "740600", "close": "740500"},
    ),
    EntitySpec(
        key="sunroof",
        platform="cover",
        name="Sunroof",
        resolve="sunroof_state",
        when="cap:sunroof",
        commands={"open": "740F01", "close": "740F00"},
    ),
    EntitySpec(
        key="liftgate",
        platform="cover",
        name="Liftgate",
        resolve="liftgate_state",
        when="cap:liftgate",
        commands={"open": "740300", "close": "740A00"},
    ),
    EntitySpec(
        key="windows_vent",
        platform="button",
        name="Windows vent",
        when="cap:windows.vent",
        commands={"press": "740E00"},
    ),
    EntitySpec(
        key="sunroof_tilt",
        platform="button",
        name="Sunroof tilt",
        when="cap:sunroof.tilt",
        commands={"press": "740F02"},
    ),
    EntitySpec(
        key="find",
        platform="button",
        name="Find car",
        when="cap:find",
        commands={"press": "740400"},
    ),
    EntitySpec(
        key="charge_stop",
        platform="button",
        name="Stop charging",
        when="cap:charging",
        commands={"press": "742701"},
    ),
    EntitySpec(
        key="engine",
        platform="switch",
        name="Engine",
        data_path="engine_on",
        when="cap:engine",
        commands={"on": "740700", "off": "740800"},
    ),
    EntitySpec(
        key="engine_on",
        platform="binary_sensor",
        name="Engine on",
        data_path="engine_on",
        when="cap:engine",
    ),
    EntitySpec(
        key="gear",
        platform="select",
        name="Gear",
        options=("low", "high"),
        when="cap:gear",
        commands={"low": "742600", "high": "742602"},
    ),
    EntitySpec(
        key="quick_cool",
        platform="button",
        name="Quick cool",
        when="cap:ac.rapidCool",
        commands={"press": "742001"},
    ),
    EntitySpec(
        key="quick_heat",
        platform="button",
        name="Quick heat",
        when="cap:ac.rapidHeat",
        commands={"press": "741F01"},
    ),
    EntitySpec(
        key="defrost_cmd",
        platform="switch",
        name="Defog",
        data_path="defrost_front",
        when="cap:ac.defog",
        commands={"on": "741201", "off": "741200"},
    ),
    EntitySpec(
        key="purify",
        platform="switch",
        name="Air purify",
        when="cap:ac.purify",
        commands={"on": "742501", "off": "742500"},
    ),
    # Front seats: live levels from blob. Rear seats: command-only (no blob yet).
    EntitySpec(
        key="seat_heatL",
        platform="select",
        name="Driver seat heat",
        data_path="seat_heat_l",
        resolve="seat_level",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.heatL",
        commands={"off": "741500", "L1": "741501", "L2": "741502", "L3": "741503"},
    ),
    EntitySpec(
        key="seat_ventL",
        platform="select",
        name="Driver seat vent",
        data_path="seat_vent_l",
        resolve="seat_level",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.ventL",
        commands={"off": "741A00", "L1": "741A01", "L2": "741A02", "L3": "741A03"},
    ),
    EntitySpec(
        key="seat_heatR",
        platform="select",
        name="Passenger seat heat",
        data_path="seat_heat_r",
        resolve="seat_level",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.heatR",
        commands={"off": "741600", "L1": "741601", "L2": "741602", "L3": "741603"},
    ),
    EntitySpec(
        key="seat_ventR",
        platform="select",
        name="Passenger seat vent",
        data_path="seat_vent_r",
        resolve="seat_level",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.ventR",
        commands={"off": "741B00", "L1": "741B01", "L2": "741B02", "L3": "741B03"},
    ),
    EntitySpec(
        key="seat_heatLR",
        platform="select",
        name="Rear L seat heat",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.heatLR",
        commands={"off": "741700", "L1": "741701", "L2": "741702", "L3": "741703"},
    ),
    EntitySpec(
        key="seat_ventLR",
        platform="select",
        name="Rear L seat vent",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.ventLR",
        commands={"off": "741C00", "L1": "741C01", "L2": "741C02", "L3": "741C03"},
    ),
    EntitySpec(
        key="seat_heatRR",
        platform="select",
        name="Rear R seat heat",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.heatRR",
        commands={"off": "741900", "L1": "741901", "L2": "741902", "L3": "741903"},
    ),
    EntitySpec(
        key="seat_ventRR",
        platform="select",
        name="Rear R seat vent",
        options=("off", "L1", "L2", "L3"),
        when="cap:seats.ventRR",
        commands={"off": "741E00", "L1": "741E01", "L2": "741E02", "L3": "741E03"},
    ),
)


def opcode_for_entity(key: str, action: str) -> str | None:
    spec = next((s for s in ENTITY_SPECS if s.key == key), None)
    if not spec:
        return None
    return spec.resolve_opcode(action)


def _cap_get(caps: dict, path: str) -> Any:
    cur: Any = caps or {}
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _when_phev(state: dict, _caps: dict) -> bool:
    return state.get("powertrain") == "phev"


def _when_direct_tpms(state: dict, _caps: dict) -> bool:
    return state.get("tyre_indirect") is False


def _cap_windows(caps: dict) -> bool:
    w = caps.get("windows") or {}
    return bool(w.get("open") or w.get("close") or w.get("vent"))


def _cap_sunroof(caps: dict) -> bool:
    r = caps.get("sunroof") or {}
    return bool(r.get("open") or r.get("tilt"))


def _cap_liftgate(caps: dict) -> bool:
    return bool(caps.get("liftgate") or caps.get("trunk"))


def _cap_seat(caps: dict, path: str) -> bool:
    sk = path.split(".", 1)[1]
    seats = caps.get("seats") or {}
    try:
        return int(seats.get(sk) or 0) > 0
    except (TypeError, ValueError):
        return False


def _cap_default(caps: dict, path: str) -> bool:
    val = _cap_get(caps, path)
    if isinstance(val, (int, float)):
        return val > 0
    return bool(val)


_WHEN: dict[str, Callable[[dict, dict], bool]] = {
    "phev": _when_phev,
    "direct_tpms": _when_direct_tpms,
}

# Exact cap: paths with non-default truthiness. seats.* uses startswith below.
_CAP_WHEN: dict[str, Callable[[dict], bool]] = {
    "windows": _cap_windows,
    "sunroof": _cap_sunroof,
    "liftgate": _cap_liftgate,
}


def _when_ok(when: str | None, state: dict, caps: dict) -> bool:
    if not when:
        return True
    fn = _WHEN.get(when)
    if fn:
        return fn(state, caps)
    if when.startswith("cap:"):
        path = when[4:]
        if path.startswith("seats."):
            return _cap_seat(caps, path)
        cap_fn = _CAP_WHEN.get(path)
        if cap_fn:
            return cap_fn(caps)
        return _cap_default(caps, path)
    return True


def get_entity_specs(
    platform: str | None = None,
    *,
    state: dict | None = None,
    caps: dict | None = None,
) -> list[EntitySpec]:
    state = state or {}
    caps = caps or {}
    out = []
    for spec in ENTITY_SPECS:
        if platform and spec.platform != platform:
            continue
        if not _when_ok(spec.when, state, caps):
            continue
        out.append(spec)
    return out


def spec_as_dict(spec: EntitySpec) -> dict:
    d = asdict(spec)
    if d.get("options") is not None:
        d["options"] = list(d["options"])
    if d.get("commands"):
        d["commands"] = dict(d["commands"])
    return d
