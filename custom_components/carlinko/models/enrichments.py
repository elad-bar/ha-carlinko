"""Derived live-state enrichments (charging, fuel, TPMS, moving, …)."""
from __future__ import annotations

from ..common.consts import BLOB, BLOB_ENRICHMENTS, KPA_TO_PSI, TPMS_POS, TYRE_INVALID
from ..common.helpers import pressure, temp


class Enrichments:
    """Section-gated enrichments over one status blob → new_data."""

    def __init__(self, blob, new_data, ctx, enrich_fns=None):
        self.blob = blob
        self.new_data = new_data
        self.ctx = ctx or {}
        self.enrich_fns = enrich_fns if enrich_fns is not None else {
            "charging": self.enrich_charging,
            "powertrain": self.enrich_powertrain,
            "fuel": self.enrich_fuel,
            "tpms": self.enrich_tpms,
            "moving": self.enrich_moving,
            "volt12_status": self.enrich_volt12_status,
        }

    def enrich_charging(self):
        charge_mode = self.new_data.get("charge_mode")
        charge_state = self.new_data.get("charge_state")
        charge_remain = self.new_data.get("charge_remain_calculated")
        charge_power = self.new_data.get("charge_power_calculated")
        self.new_data["charging"] = {
            "active": charge_state == 1,
            "mode": {16: "dc", 1: "ac"}.get(charge_mode) or "none",
            "state": charge_state,
            "remaining_min": charge_remain,
            "rate_kw": charge_power if charge_state == 1 else 0,
        }

    def enrich_powertrain(self):
        fuel_pct = self.new_data.get("fuel_pct")
        fuel_l_100 = self.new_data.get("fuel_l_100_calculated")
        cfg_pt = self.ctx.get("powertrain_cfg") or "auto"
        phev = cfg_pt == "phev" or (cfg_pt == "auto" and bool(fuel_pct or fuel_l_100))
        self.new_data["powertrain"] = "phev" if phev else "bev"

    def enrich_fuel(self):
        if self.new_data.get("powertrain") != "phev":
            self.new_data["fuel"] = None
            return
        fuel_pct = self.new_data.get("fuel_pct")
        fuel_l_100 = self.new_data.get("fuel_l_100_calculated")
        ev = self.new_data.get("range")
        headline_range = self.new_data.get("headline_range")
        self.new_data["fuel"] = {
            "pct": fuel_pct,
            "l_100": fuel_l_100,
            "range_km": headline_range,
            "total_range_km": (
                (ev + headline_range)
                if (ev is not None and headline_range is not None)
                else None
            ),
        }

    def enrich_tpms(self):
        ty_s, ty_e = BLOB["tyres"]
        if len(self.blob) < ty_e:
            return
        tb = self.blob[ty_s:ty_e]
        if not any(x != TYRE_INVALID for x in tb):
            return
        scale = self.ctx.get("tpms_scale")
        unit = self.ctx.get("tyre_unit") or "psi"
        self.new_data["tpms"] = [
            {
                "pos": TPMS_POS[i],
                "psi": pressure(tb[i], scale, unit),
                "temp": temp(tb[4 + i]),
                "valid": tb[i] != TYRE_INVALID,
            }
            for i in range(4)
        ]
        raw_psi = [
            (None if tb[i] == TYRE_INVALID else tb[i] * scale * KPA_TO_PSI)
            for i in range(4)
        ]
        raw_psi = [p for p in raw_psi if p is not None]
        if raw_psi:
            self.new_data["tyre_indirect"] = False
            self.new_data["tyre_status"] = (
                "Check tyres" if any(p < 28 or p > 40 for p in raw_psi) else "Normal"
            )

    def enrich_moving(self):
        odo = self.new_data.get("odo")
        prev_odo = self.ctx.get("prev_odo")
        if prev_odo is not None and odo is not None and odo > prev_odo:
            self.new_data["moving"] = True

    def enrich_volt12_status(self):
        v12 = self.new_data.get("volt12_calculated")
        if v12 is not None:
            self.new_data["volt12_status"] = (
                "critical" if v12 < 12.0 else ("low" if v12 < 12.5 else "ok")
            )

    def apply(self, enrichments=BLOB_ENRICHMENTS):
        """Run section-gated enrichments in table order."""
        n = len(self.blob)
        for enrich_id, section in enrichments:
            if n <= section.value:
                continue
            fn = self.enrich_fns.get(enrich_id)
            if fn:
                fn()
