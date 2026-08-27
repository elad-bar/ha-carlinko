"""Section-gated status-blob field extract + optional scaling."""
from __future__ import annotations

from .consts import BLOB, BLOB_FIELDS


class BlobFields:
    """Extract BLOB_FIELDS into new_data for one status blob."""

    def __init__(self, blob, new_data, readers=None, calcs=None):
        self.blob = blob
        self.new_data = new_data
        self.readers = readers if readers is not None else {
            "byte": self.blob_byte,
            "int": self.blob_int,
            "flag": self.blob_flag,
        }
        self.calcs = calcs if calcs is not None else {
            "volt12": self.calc_volt12,
            "speed": self.calc_speed,
            "consumption": self.calc_consumption,
            "fuel_l_100": self.calc_fuel_l_100,
            "charge_remain": self.calc_charge_remain,
            "charge_power": self.calc_charge_power,
            "ac_temp": self.calc_ac_temp,
        }

    def blob_int(self, key):
        s, e = BLOB[key]
        return int.from_bytes(self.blob[s:e], "big")

    def blob_byte(self, key):
        return self.blob[BLOB[key]]

    def blob_flag(self, key):
        return self.blob[BLOB[key]] != 0

    @staticmethod
    def calc_volt12(v):
        return round(v * BLOB["volt12_scale"], 2)

    @staticmethod
    def calc_speed(v):
        return round(v / BLOB["speed_div"], 1)

    @staticmethod
    def calc_consumption(v):
        scaled = round(v * BLOB["consumption_scale"], 1)
        return scaled or None

    @staticmethod
    def calc_fuel_l_100(v):
        return round(v * BLOB["fuel_l_100_scale"], 1)

    @staticmethod
    def calc_charge_remain(v):
        return None if v >= BLOB["charge_remain_invalid"] else v

    @staticmethod
    def calc_charge_power(v):
        return round(v * BLOB["charge_power_scale"], 1)

    @staticmethod
    def calc_ac_temp(v):
        return v if 16 <= v <= 30 else None

    def apply(self, fields=BLOB_FIELDS):
        """Filter by len(blob) vs BlobSection, then extract + optional calc."""
        n = len(self.blob)
        for key, reader_kind, calc, section in fields:
            if n <= section.value:
                continue
            reader = self.readers.get(reader_kind)
            if not reader:
                continue
            raw = reader(key)
            self.new_data[key] = raw
            if calc is not None:
                dest, calc_id = calc
                fn = self.calcs.get(calc_id)
                if fn:
                    self.new_data[dest] = fn(raw)
