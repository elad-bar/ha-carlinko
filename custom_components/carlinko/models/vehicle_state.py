"""Live vehicle state manager: status blob → enriched live dict (no SQLite)."""
from __future__ import annotations

import copy
import re
import time

from .blob_fields import BlobFields
from ..common.consts import (
    DEFAULT_BATTERY_KWH,
    DEFAULT_CHEMISTRY,
    DEFAULT_TPMS_SCALE,
    EMPTY_VEHICLE_STATE,
    KNOWN_CAR_OVERRIDES,
)
from .enrichments import Enrichments


def _norm_model_name(s):
    """Lowercase words; "j5" and "5" treated the same (regional naming varies)."""
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
    return re.sub(r"\bj(\d)\b", r"\1", s).strip()


def _match_car_overrides(table, model):
    """Row from table whose key words all appear in model; longest key wins."""
    name = " " + _norm_model_name(model) + " "
    if not name.strip():
        return None
    best = None
    for key, val in table.items():
        words = _norm_model_name(key).split()
        if words and all(f" {w} " in name for w in words) and (
            best is None or len(words) > best[0]
        ):
            best = (len(words), val)
    return best[1] if best else None


class VehicleState:
    """Owns live state: metadata from config, car fields from status blobs."""

    def __init__(self):
        self.data = copy.deepcopy(EMPTY_VEHICLE_STATE)
        self._powertrain_cfg = "auto"
        self._tpms_scale = DEFAULT_TPMS_SCALE
        self._chemistry = DEFAULT_CHEMISTRY

    def update_metadata(self, creds):
        """Apply vehicle / tariff / TPMS from store data into self.data."""
        creds = creds or {}
        v = creds.get("vehicle") or {}
        model = v.get("model") or "EV"
        known = _match_car_overrides(KNOWN_CAR_OVERRIDES, model) or {}

        self._powertrain_cfg = (
            creds.get("powertrain") or known.get("powertrain") or "auto"
        ).lower()
        self._tpms_scale = float(
            creds.get("tpms_scale") or known.get("tpms_scale") or DEFAULT_TPMS_SCALE
        )
        self._chemistry = (
            creds.get("chemistry") or known.get("chemistry") or DEFAULT_CHEMISTRY
        ).lower()

        tariff = creds.get("tariff")

        self.data.update(
            {
                "vehicle": {
                    "plate": v.get("plate") or "—",
                    "model": model,
                    "vin": v.get("vin") or "—",
                },
                "battery_kwh": float(
                    creds.get("battery_kwh")
                    or known.get("battery_kwh")
                    or DEFAULT_BATTERY_KWH
                ),
                "tyre_unit": (creds.get("tyre_unit") or "psi").lower(),
                "tariff": tariff,
            }
        )
        return self.data

    def update_data(self, hexstr):
        """Parse action:6 status blob into a local copy, then commit to self.data."""
        new_data = dict(self.data)
        ts = int(time.time())
        new_data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        new_data["updated_ts"] = ts
        new_data["online"] = True
        new_data["age_min"] = 0.0
        new_data["moving"] = False

        b = bytes.fromhex(hexstr)
        BlobFields(b, new_data).apply()
        ctx = {
            "powertrain_cfg": self._powertrain_cfg,
            "tpms_scale": self._tpms_scale,
            "tyre_unit": new_data.get("tyre_unit"),
            "prev_odo": self.data.get("odo"),
        }
        Enrichments(b, new_data, ctx).apply()

        self.data.update(new_data)
        return self.data
