"""Map HA-free EntitySpec → Home Assistant EntityDescription subclasses.

May import homeassistant. Platforms should use descriptions from here rather than
building HA attrs from the catalog directly.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.cover import CoverEntityDescription
from homeassistant.components.lock import LockEntityDescription
from homeassistant.components.number import NumberDeviceClass, NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory, EntityDescription

from ..models.entity_specs import EntitySpec

_SENSOR_DEVICE_CLASS = {v.value: v for v in SensorDeviceClass}
_SENSOR_STATE_CLASS = {v.value: v for v in SensorStateClass}
_BINARY_DEVICE_CLASS = {v.value: v for v in BinarySensorDeviceClass}

_UNIT_MAP: dict[str, str] = {
    "km": UnitOfLength.KILOMETERS,
    "km/h": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "psi": UnitOfPressure.PSI,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "°C": UnitOfTemperature.CELSIUS,
    "V": UnitOfElectricPotential.VOLT,
    "kW": UnitOfPower.KILO_WATT,
    "min": UnitOfTime.MINUTES,
    "%": PERCENTAGE,
}

# Cost knobs (account-level).
_CONFIG_KEYS = frozenset({"tariff", "petrol_price", "petrol_kml"})

# Derived / detail sensors — diagnostic category (enabled by default).
_DIAGNOSTIC_KEYS = frozenset(
    {
        "hv_state",
        "volt12",
        "volt12_status",
        "tyre_fl_temp",
        "tyre_fr_temp",
        "tyre_rl_temp",
        "tyre_rr_temp",
        "charge_power",
        "consumption",
        "charge_remaining",
        "charge_mode",
    }
)


def _map_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    return _UNIT_MAP.get(unit, unit)


def _category_kwargs(spec: EntitySpec) -> dict:
    if spec.key in _CONFIG_KEYS:
        return {"entity_category": EntityCategory.CONFIG}
    if spec.key in _DIAGNOSTIC_KEYS:
        return {"entity_category": EntityCategory.DIAGNOSTIC}
    return {}


def get_entity_description(spec: EntitySpec) -> EntityDescription:
    """Build the HA EntityDescription for a catalog spec."""
    base: dict = {
        "key": spec.key,
        "translation_key": spec.key,
        **_category_kwargs(spec),
    }
    if spec.icon:
        base["icon"] = spec.icon

    platform = spec.platform
    if platform == "sensor":
        kwargs = dict(base)
        unit = _map_unit(spec.unit)
        if unit:
            kwargs["native_unit_of_measurement"] = unit
        if spec.device_class:
            kwargs["device_class"] = _SENSOR_DEVICE_CLASS.get(spec.device_class)
        if spec.state_class:
            kwargs["state_class"] = _SENSOR_STATE_CLASS.get(spec.state_class)
        if spec.options:
            kwargs["options"] = list(spec.options)
        return SensorEntityDescription(**kwargs)

    if platform == "binary_sensor":
        kwargs = dict(base)
        if spec.device_class:
            kwargs["device_class"] = _BINARY_DEVICE_CLASS.get(spec.device_class)
        return BinarySensorEntityDescription(**kwargs)

    if platform == "number":
        kwargs = dict(base)
        if spec.key in ("tariff", "petrol_price"):
            kwargs["device_class"] = NumberDeviceClass.MONETARY
        else:
            unit = _map_unit(spec.unit)
            if unit:
                kwargs["native_unit_of_measurement"] = unit
        return NumberEntityDescription(**kwargs)

    if platform == "select":
        return SelectEntityDescription(**base)
    if platform == "lock":
        return LockEntityDescription(**base)
    if platform == "climate":
        return ClimateEntityDescription(**base)
    if platform == "cover":
        return CoverEntityDescription(**base)
    if platform == "button":
        return ButtonEntityDescription(**base)
    if platform == "switch":
        return SwitchEntityDescription(**base)
    if platform == "device_tracker":
        return EntityDescription(**base)

    return EntityDescription(**base)
