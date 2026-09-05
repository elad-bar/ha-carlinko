"""CarLinko vehicle CDN image entities (Front / Side / Top)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .common.base_entity import CarlinkoEntity
from .common.entity_setup import async_setup_entities
from .managers.coordinator import CarlinkoCoordinator
from .models.entity_specs import EntitySpec
from .models.vehicle_images import angle_from_entity_key

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarlinkoCoordinator = entry.runtime_data
    async_setup_entities(
        hass,
        entry,
        coordinator,
        "image",
        async_add_entities,
        CarlinkoImage,
    )


class CarlinkoImage(CarlinkoEntity, ImageEntity):
    def __init__(
        self, coordinator: CarlinkoCoordinator, spec: EntitySpec, vehicle_id: str
    ) -> None:
        CarlinkoEntity.__init__(self, coordinator, spec, vehicle_id)
        ImageEntity.__init__(self, coordinator.hass)
        self._angle = angle_from_entity_key(spec.key) or "front"

    def _cached(self) -> dict:
        return self.coordinator.store.get_vehicle_image(
            self.vehicle_id, angle=self._angle
        )

    def _image_bytes(self) -> bytes | None:
        raw = self._cached().get("data")
        if not raw:
            return None
        try:
            return base64.b64decode(str(raw))
        except Exception:
            return None

    @property
    def available(self) -> bool:
        if not self._image_bytes():
            return False
        return super().available

    @property
    def content_type(self) -> str:
        ctype = str(self._cached().get("content_type") or "").strip()
        return ctype or "image/jpeg"

    @property
    def image_last_updated(self) -> datetime | None:
        updated = self._cached().get("updated")
        if updated is None:
            return None
        try:
            return datetime.fromtimestamp(float(updated), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

    async def async_image(self) -> bytes | None:
        return self._image_bytes()
