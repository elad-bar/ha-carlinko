"""Base CarLinko entity + shared helpers."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..managers.coordinator import CarlinkoCoordinator
from ..common.consts import DOMAIN
from .entity_specs import EntitySpec
from .entity_values import EntityValueResolver


class CarlinkoEntity(CoordinatorEntity[CarlinkoCoordinator]):
    """Coordinator entity backed by an EntitySpec for one vehicle."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CarlinkoCoordinator,
        spec: EntitySpec,
        vehicle_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.spec = spec
        self.vehicle_id = str(vehicle_id)
        self._resolver = EntityValueResolver(coordinator.store)
        self._attr_unique_id = f"carlinko_{self.vehicle_id}_{spec.key}"
        self._attr_name = spec.name
        if spec.icon:
            self._attr_icon = spec.icon
        meta = coordinator.store.get_vehicle_meta(self.vehicle_id)
        vehicle = coordinator.vehicle_data(self.vehicle_id).get("vehicle") or {
            "plate": meta.get("plate") or "—",
            "model": meta.get("model") or "EV",
            "vin": meta.get("vin") or "—",
        }
        model = vehicle.get("model") or meta.get("model") or "CarLinko"
        vin = vehicle.get("vin") or meta.get("vin") or self.vehicle_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.vehicle_id)},
            name=vehicle.get("plate") or meta.get("plate") or model,
            manufacturer="CarLinko",
            model=model,
            serial_number=vin if vin and vin != "—" else None,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_available(self.vehicle_id)

    def _state_value(self):
        return self._resolver.resolve_value(
            self.spec, self.coordinator.vehicle_data(self.vehicle_id)
        )

    async def _async_send_action(self, action: str) -> None:
        opcode = self.spec.resolve_opcode(action)
        if not opcode:
            raise ValueError(f"no opcode for {self.spec.key}/{action}")
        await self.coordinator.async_send_control(opcode, vehicle_id=self.vehicle_id)
