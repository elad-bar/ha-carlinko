"""Base CarLinko entity + shared helpers."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..managers.coordinator import CarlinkoCoordinator
from ..common.consts import DOMAIN
from .entity_specs import EntitySpec
from .entity_values import EntityValueResolver


class CarlinkoEntity(CoordinatorEntity[CarlinkoCoordinator]):
    """Coordinator entity backed by an EntitySpec."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CarlinkoCoordinator, spec: EntitySpec) -> None:
        super().__init__(coordinator)
        self.spec = spec
        self._resolver = EntityValueResolver(coordinator.store)
        self._attr_unique_id = f"carlinko_{coordinator.vehicle_id}_{spec.key}"
        self._attr_name = spec.name
        if spec.icon:
            self._attr_icon = spec.icon
        vehicle = (coordinator.data or {}).get("vehicle") or coordinator.store.get_vehicle()
        model = vehicle.get("model") or "CarLinko"
        vin = vehicle.get("vin") or coordinator.vehicle_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.vehicle_id)},
            name=vehicle.get("plate") or model,
            manufacturer="CarLinko",
            model=model,
            serial_number=vin if vin and vin != "—" else None,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_available()

    def _state_value(self):
        return self._resolver.resolve_value(self.spec, self.coordinator.data or {})

    async def _async_send_action(self, action: str) -> None:
        opcode = self.spec.resolve_opcode(action)
        if not opcode:
            raise ValueError(f"no opcode for {self.spec.key}/{action}")
        await self.coordinator.async_send_control(opcode)
