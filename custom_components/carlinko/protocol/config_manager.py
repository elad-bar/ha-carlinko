"""Persisted app config + session token (`data/config.json`) — not API/WS logic."""
from __future__ import annotations

import json
import logging
import os
import tempfile

from .consts import DEFAULT_PETROL_KML, DEFAULT_PETROL_PRICE, DEFAULT_TARIFF

_LOGGER = logging.getLogger(__name__)

# protocol/ → carlinko/ → custom_components/ → repo root
_PROTOCOL = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_PROTOCOL)))

# Keys that belong in env, never in config.json
_SECRET_KEYS = frozenset({"email", "password", "region"})


def data_dir():
    return os.environ.get("CARLINKO_DATA") or os.path.join(_REPO, "data")


def config_path():
    return os.path.join(data_dir(), "config.json")


class ConfigManager:
    """Load / save `config.json` under CARLINKO_DATA (default: repo `data/`)."""

    def __init__(self, path=None):
        self.path = path or config_path()
        self.data = {}
        self._migrate_if_needed()
        self.load()

    def load(self):
        try:
            raw = json.load(open(self.path, encoding="utf-8"))
            self.data = raw if isinstance(raw, dict) else {}
        except Exception:
            self.data = {}
        return self.data

    def save(self, data=None):
        if data is not None:
            self.data = dict(data)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self.path) or ".",
            prefix=".config.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass
        return self.data

    def update(self, **kwargs):
        self.data.update(kwargs)
        return self.save()

    def set_token(self, token):
        self.data["token"] = token or ""
        return self.save()

    def get_cost_config(self):
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

    def set_cost_config(self, key, value):
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
        self.load()
        c = dict(self.data)
        if key == "tariff":
            c["tariff"] = int(v) if v == int(v) else v
            c.pop("tariff_idr", None)
        else:
            c[key] = v
        self.save(c)
        return {"ok": True, "key": key, "value": self.get_cost_config()[key]}

    def get_vehicle(self):
        v = self.data.get("vehicle") or {}
        return {
            "plate": v.get("plate") or "—",
            "model": v.get("model") or "EV",
            "vin": v.get("vin") or "—",
        }

    def get_vehicle_id(self):
        return str(self.data.get("vehicle_id") or "")

    def _migrate_if_needed(self):
        """One-shot: old creds.json (+ token.txt) → config.json without secrets."""
        if os.path.isfile(self.path):
            return
        root = os.path.dirname(self.path) or "."
        old_creds = os.path.join(root, "creds.json")
        alt_creds = os.path.join(_PROTOCOL, "creds.json")
        src = old_creds if os.path.isfile(old_creds) else (
            alt_creds if os.path.isfile(alt_creds) else None
        )
        if not src:
            return
        try:
            raw = json.load(open(src, encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        out = {k: v for k, v in raw.items() if k not in _SECRET_KEYS}
        token_file = os.path.join(os.path.dirname(src), "token.txt")
        if not out.get("token") and os.path.isfile(token_file):
            try:
                out["token"] = open(token_file, encoding="utf-8").read().strip()
            except Exception:
                pass
        self.data = out
        self.save()
        _LOGGER.info(
            "migrated %s → %s (set CARLINKO_EMAIL / CARLINKO_PASSWORD / "
            "CARLINKO_REGION in .env)",
            src,
            self.path,
        )
