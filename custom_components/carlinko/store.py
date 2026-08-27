"""HA Store-backed config implementing protocol ConfigAdapter."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .protocol.consts import DEFAULT_PETROL_KML, DEFAULT_PETROL_PRICE, DEFAULT_TARIFF


class CarlinkoStore:
    """Persist token / vehicle ids / cost knobs via hass helpers.storage.Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
        )
        self.data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        raw = await self._store.async_load()
        self.data = dict(raw) if isinstance(raw, dict) else {}
        return self.data

    def load(self) -> dict[str, Any]:
        """Sync load is a no-op for HA; data comes from async_load."""
        return self.data

    def save(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if data is not None:
            self.data = dict(data)
        self.hass.async_create_task(self._store.async_save(self.data))
        return self.data

    async def async_save(self) -> None:
        await self._store.async_save(self.data)

    def update(self, **kwargs: Any) -> dict[str, Any]:
        self.data.update(kwargs)
        return self.save()

    def set_token(self, token: str | None) -> dict[str, Any]:
        self.data["token"] = token or ""
        return self.save()

    def get_cost_config(self) -> dict[str, Any]:
        c = self.data
        cur = c.get("currency") or {}
        raw = c.get("tariff")
        if raw is None:
            raw = c.get("tariff_idr")
        t = float(raw if raw is not None else DEFAULT_TARIFF)
        tariff = int(t) if t == int(t) else t
        return {
            "tariff": tariff,
            "petrol_price": float(c.get("petrol_price") or DEFAULT_PETROL_PRICE),
            "petrol_kml": float(c.get("petrol_kml") or DEFAULT_PETROL_KML),
            "currency": {
                "symbol": cur.get("symbol") or "Rp",
                "locale": cur.get("locale") or "id-ID",
                "code": (cur.get("code") or "IDR").upper(),
            },
        }

    def set_cost_config(self, key: str, value: Any) -> dict[str, Any]:
        if key not in ("tariff", "petrol_price", "petrol_kml"):
            return {"ok": False, "error": "unknown key"}
        try:
            v = float(value)
        except Exception:
            return {"ok": False, "error": "not a number"}
        if v < 0:
            return {"ok": False, "error": "negative"}
        maxes = {"tariff": 1e7, "petrol_price": 1e7, "petrol_kml": 100}
        if v > maxes[key]:
            return {"ok": False, "error": "out of range"}
        if key == "petrol_kml" and v <= 0:
            return {"ok": False, "error": "petrol_kml must be > 0"}
        if key == "tariff":
            self.data["tariff"] = int(v) if v == int(v) else v
            self.data.pop("tariff_idr", None)
        else:
            self.data[key] = v
        self.save()
        return {"ok": True, "key": key, "value": self.get_cost_config()[key]}

    def get_vehicle(self) -> dict[str, Any]:
        v = self.data.get("vehicle") or {}
        return {
            "plate": v.get("plate") or "—",
            "model": v.get("model") or "EV",
            "vin": v.get("vin") or "—",
        }

    def get_vehicle_id(self) -> str:
        return str(self.data.get("vehicle_id") or "")
