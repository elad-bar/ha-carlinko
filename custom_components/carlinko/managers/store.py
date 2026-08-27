"""Session / cost / vehicle persistence — one store for HA and engine.

HA: wraps ``homeassistant.helpers.storage.Store`` (lazy import).
Engine: same class, JSON file under ``CARLINKO_DATA`` / repo ``data/``.
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


class CarlinkoStore:
    """Persist token / vehicle ids / cost knobs.

    Construct with ``(hass, entry_id)`` for Home Assistant, or ``path=...`` /
    ``CarlinkoStore.for_engine()`` for the CLI harness.
    """

    def __init__(
        self,
        hass: Any | None = None,
        entry_id: str | None = None,
        *,
        path: str | None = None,
    ) -> None:
        self.data: dict[str, Any] = {}
        self.hass = hass
        self._path: str | None = None
        self._ha_store: Any | None = None

        if hass is not None:
            if not entry_id:
                raise ValueError("entry_id is required when hass is set")
            # Lazy so engine can import this module without Home Assistant.
            from homeassistant.helpers.storage import Store

            self._ha_store = Store(
                hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
            )
            return

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
        if self._path is not None:
            self.load()
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
