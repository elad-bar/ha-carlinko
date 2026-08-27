"""Session / cost / vehicle persistence — one store for HA and engine.

HA path: pass a pre-built ``homeassistant.helpers.storage.Store`` via ``ha_store=``
(constructed in HA-facing modules). This module never imports Home Assistant.

Engine: JSON file under ``CARLINKO_DATA`` / repo ``data/``.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from ..common.consts import (
    DEFAULT_PETROL_KML,
    DEFAULT_PETROL_PRICE,
    DEFAULT_TARIFF,
    STORAGE_KEY,
    STORAGE_VERSION,
)

# managers/ → carlinko/ → custom_components/ → repo root
_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def data_dir() -> str:
    return os.environ.get("CARLINKO_DATA") or os.path.join(_REPO, "data")


def config_path() -> str:
    """Engine JSON path (default: repo ``data/config.json``)."""
    return os.path.join(data_dir(), "config.json")


def ha_storage_key(entry_id: str) -> str:
    """Storage key for HA ``Store`` (built by HA-facing callers)."""
    return f"{STORAGE_KEY}.{entry_id}"


class CarlinkoStore:
    """Persist token / vehicle ids / cost knobs.

    HA: ``CarlinkoStore(hass, ha_store=Store(...))``.
    Engine: ``CarlinkoStore.for_engine()`` / ``path=...``.
    """

    def __init__(
        self,
        hass: Any | None = None,
        entry_id: str | None = None,
        *,
        path: str | None = None,
        ha_store: Any | None = None,
    ) -> None:
        self.data: dict[str, Any] = {}
        self.hass = hass
        self._path: str | None = None
        self._ha_store: Any | None = None

        if ha_store is not None:
            self._ha_store = ha_store
            return

        if hass is not None:
            raise ValueError(
                "HA store requires ha_store= (construct Store in HA-facing code; "
                f"key={ha_storage_key(entry_id or '')!r}, version={STORAGE_VERSION})"
            )

        self._path = path or config_path()
        self.load()

    @classmethod
    def for_engine(cls, path: str | None = None) -> CarlinkoStore:
        """File-backed store for ``engine/entrypoint.py``."""
        return cls(path=path or config_path())

    async def async_load(self) -> dict[str, Any]:
        if self._ha_store is not None:
            raw = await self._ha_store.async_load()
            self.data = dict(raw) if isinstance(raw, dict) else {}
            return self.data
        return self.load()

    def load(self) -> dict[str, Any]:
        if self._ha_store is not None:
            # Sync load is a no-op for HA; data comes from async_load.
            return self.data
        assert self._path is not None
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            self.data = raw if isinstance(raw, dict) else {}
        except Exception:
            self.data = {}
        return self.data

    def save(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if data is not None:
            self.data = dict(data)
        if self._ha_store is not None:
            self.hass.async_create_task(self._ha_store.async_save(self.data))
            return self.data
        return self._save_file()

    async def async_save(self) -> None:
        if self._ha_store is not None:
            await self._ha_store.async_save(self.data)
            return
        self._save_file()

    async def async_remove(self) -> None:
        """Delete persisted HA store so tokens do not linger after entry removal."""
        if self._ha_store is not None:
            await self._ha_store.async_remove()
            self.data = {}
            return
        if self._path and os.path.isfile(self._path):
            try:
                os.unlink(self._path)
            except OSError:
                pass
        self.data = {}

    def _save_file(self) -> dict[str, Any]:
        assert self._path is not None
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self._path) or ".",
            prefix=".config.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        try:
            os.chmod(self._path, 0o600)
        except Exception:
            pass
        return self.data

    def update(self, **kwargs: Any) -> dict[str, Any]:
        self.data.update(kwargs)
        return self.save()

    def set_token(self, token: str | None) -> dict[str, Any]:
        self.data["token"] = token or ""
        return self.save()

    def get_cost_config(self) -> dict[str, Any]:
        c = self.data
        raw = c.get("tariff")
        t = float(raw if raw is not None else DEFAULT_TARIFF)
        tariff = int(t) if t == int(t) else t
        return {
            "tariff": tariff,
            "petrol_price": float(c.get("petrol_price") or DEFAULT_PETROL_PRICE),
            "petrol_kml": float(c.get("petrol_kml") or DEFAULT_PETROL_KML),
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
        if self._path is not None:
            self.load()
        if key == "tariff":
            self.data["tariff"] = int(v) if v == int(v) else v
        else:
            self.data[key] = v
        self.save()
        return {"ok": True, "key": key, "value": self.get_cost_config()[key]}

    def get_vehicles(self) -> dict[str, dict[str, Any]]:
        """Map of vehicle_id → metadata (device_sn, plate, model, vin)."""
        raw = self.data.get("vehicles")
        if isinstance(raw, dict) and raw:
            return {
                str(vid): dict(meta) if isinstance(meta, dict) else {}
                for vid, meta in raw.items()
            }
        # Legacy single-vehicle shape → synthetic map.
        vid = str(self.data.get("vehicle_id") or "")
        if not vid:
            return {}
        v = self.data.get("vehicle") or {}
        return {
            vid: {
                "vehicle_id": vid,
                "device_sn": str(self.data.get("device_sn") or ""),
                "plate": v.get("plate") or "—",
                "model": v.get("model") or "EV",
                "vin": v.get("vin") or "—",
            }
        }

    def get_vehicle_meta(self, vehicle_id: str) -> dict[str, Any]:
        return dict(self.get_vehicles().get(str(vehicle_id)) or {})

    def set_vehicles(self, vehicles: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Persist hub vehicles map and mirror first car into legacy keys."""
        cleaned: dict[str, dict[str, Any]] = {}
        for vid, meta in (vehicles or {}).items():
            key = str(vid)
            if not key:
                continue
            m = dict(meta or {})
            m["vehicle_id"] = key
            cleaned[key] = m
        self.data["vehicles"] = cleaned
        if cleaned:
            first_id = next(iter(cleaned))
            first = cleaned[first_id]
            self.data["vehicle_id"] = first_id
            self.data["device_sn"] = str(first.get("device_sn") or "")
            self.data["vehicle"] = {
                "plate": first.get("plate") or "—",
                "model": first.get("model") or "EV",
                "vin": first.get("vin") or "—",
            }
        else:
            self.data.pop("vehicle_id", None)
            self.data.pop("device_sn", None)
            self.data.pop("vehicle", None)
        return self.save()

    def get_vehicle(self, vehicle_id: str | None = None) -> dict[str, Any]:
        if vehicle_id:
            meta = self.get_vehicle_meta(vehicle_id)
            if meta:
                return {
                    "plate": meta.get("plate") or "—",
                    "model": meta.get("model") or "EV",
                    "vin": meta.get("vin") or "—",
                }
        v = self.data.get("vehicle") or {}
        return {
            "plate": v.get("plate") or "—",
            "model": v.get("model") or "EV",
            "vin": v.get("vin") or "—",
        }

    def get_vehicle_id(self) -> str:
        vehicles = self.get_vehicles()
        if vehicles:
            return next(iter(vehicles))
        return str(self.data.get("vehicle_id") or "")
