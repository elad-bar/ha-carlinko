"""All CarLinko constants (integration + wire). Keep HA-free — no homeassistant imports."""
from enum import Enum

# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------
DOMAIN = "carlinko"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_STREAM_BACKSTOP = "stream_backstop"
CONF_AVAILABILITY_SECONDS = "availability_seconds"

# Entity unavailable when last frame older than this (legacy ~40 min).
AVAILABILITY_SECONDS = 2400
CAPS_REFRESH_INTERVAL_S = 3300

KNOWN_REGIONS = ("sea",)
# Platform names; __init__ maps these to homeassistant.const.Platform.
PLATFORMS = (
    "sensor",
    "binary_sensor",
    "number",
    "lock",
    "climate",
    "cover",
    "button",
    "switch",
    "select",
)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.store"

# ---------------------------------------------------------------------------
# Protocol / hosts / headers
# ---------------------------------------------------------------------------
USER_AGENT = "Dart/3.10 (dart:io)"
DEFAULT_SIGN_KEY = "mYj3fzMpn77bir66"
DEFAULT_REGION = "sea"
API_HOST_TMPL = "https://cqr-api-{region}.hzhjcl.com"
WS_HOST_TMPL = "ws://wss-cqr-{region}.hzhjcl.com:4002/"
OK_CODE = "0000"
STALE_TOKEN_CODES = frozenset({"9997", "40001", "40003", "401", "1001", "1002"})
DEFAULT_PORT = 8088

# Static device/app fields for POST /user/login (account/password/dateTime filled at call time).
LOGIN_BODY_DEFAULTS = {
    "method": "PASSWORD",
    "appType": "APP",
    "osType": "ANDROID",
    "appName": "CarLinko",
    "appVersion": "1.12.0",
    "osVersion": "13",
    "language": "en",
    "timeZone": "Asia/Jakarta",
    "phoneBrand": "Google",
    "phoneModel": "Pixel 7 Pro",
    "md5": "",
    "verifyCode": "",
}

# ---------------------------------------------------------------------------
# Blob layout + enums (action:6 status blob)
# Offsets are single ints; slices are (start, end) exclusive; scales are multipliers.
# ---------------------------------------------------------------------------
BLOB = {
    "doors": 2,
    "unlocked": 3,
    "trunk": 4,
    "hv_state": 5,
    "windows": 8,
    "sunroof": 9,
    "volt12": (12, 14),
    "volt12_scale": 0.01,
    "speed": (14, 16),
    "speed_div": 16.0,
    "odo": (18, 21),
    "fuel_pct": 21,
    "ac_on": 23,
    "ac_temp": 24,
    "engine_on": 26,
    "battery": 28,
    "range": (29, 31),
    "seat_heat_l": 32,
    "seat_heat_r": 33,
    "seat_vent_l": 37,
    "seat_vent_r": 38,
    "defrost_front": 42,
    "tyres": (44, 52),
    "fuel_l_100": 53,
    "fuel_l_100_scale": 0.1,
    "consumption": 55,
    "consumption_scale": 0.1,
    "charge_mode": 56,
    "charge_state": 57,
    "charge_remain": (58, 60),
    "charge_remain_invalid": 0x3FE,
    "charge_power": (62, 64),
    "charge_power_scale": 0.1,
    "wltc_range": (68, 70),
    "headline_range": (70, 72),
}

# Blob field extract tiers: apply a row when len(blob) > section.value.
class BlobSection(Enum):
    CORE = 30
    EXTENDED = 55
    HEAD = 71


# (blob_key, reader_kind, calc, section)
# reader_kind: "byte" | "int" | "flag"
# calc: None | (dest_key, calc_id) — calc_id resolved by BlobFields.calcs
BLOB_FIELDS = (
    ("battery", "byte", None, BlobSection.CORE),
    ("range", "int", None, BlobSection.CORE),
    ("odo", "int", None, BlobSection.CORE),
    ("unlocked", "flag", None, BlobSection.CORE),
    ("volt12", "int", ("volt12_calculated", "volt12"), BlobSection.CORE),
    ("speed", "int", ("speed_calculated", "speed"), BlobSection.CORE),
    ("consumption", "byte", ("consumption_calculated", "consumption"), BlobSection.EXTENDED),
    ("fuel_pct", "byte", None, BlobSection.EXTENDED),
    ("fuel_l_100", "byte", ("fuel_l_100_calculated", "fuel_l_100"), BlobSection.EXTENDED),
    ("charge_mode", "byte", None, BlobSection.EXTENDED),
    ("charge_state", "byte", None, BlobSection.EXTENDED),
    ("charge_remain", "int", ("charge_remain_calculated", "charge_remain"), BlobSection.EXTENDED),
    ("charge_power", "int", ("charge_power_calculated", "charge_power"), BlobSection.EXTENDED),
    ("ac_on", "flag", None, BlobSection.EXTENDED),
    ("doors", "byte", None, BlobSection.EXTENDED),
    ("trunk", "flag", None, BlobSection.EXTENDED),
    ("windows", "byte", None, BlobSection.EXTENDED),
    ("sunroof", "flag", None, BlobSection.EXTENDED),
    ("engine_on", "flag", None, BlobSection.EXTENDED),
    ("ac_temp", "byte", ("ac_temp_calculated", "ac_temp"), BlobSection.EXTENDED),
    ("seat_heat_l", "byte", None, BlobSection.EXTENDED),
    ("seat_heat_r", "byte", None, BlobSection.EXTENDED),
    ("seat_vent_l", "byte", None, BlobSection.EXTENDED),
    ("seat_vent_r", "byte", None, BlobSection.EXTENDED),
    ("defrost_front", "flag", None, BlobSection.EXTENDED),
    ("wltc_range", "int", None, BlobSection.EXTENDED),
    ("hv_state", "byte", None, BlobSection.EXTENDED),
    ("headline_range", "int", None, BlobSection.HEAD),
)

# Derived-state enrichments: (enrich_id, section) — applied when len(blob) > section.value
# enrich_id resolved by Enrichments.enrich_fns; order matters (fuel after powertrain).
BLOB_ENRICHMENTS = (
    ("charging", BlobSection.EXTENDED),
    ("powertrain", BlobSection.EXTENDED),
    ("fuel", BlobSection.EXTENDED),
    ("tpms", BlobSection.EXTENDED),
    ("moving", BlobSection.CORE),
    ("volt12_status", BlobSection.CORE),
)

CHARGE_STATE = {0: "idle", 1: "charging", 2: "complete", 3: "canceled", 4: "hot", 5: "stop"}
HV_STATE = {0: "off", 1: "lv", 2: "ready"}
TPMS_POS = ["FL", "FR", "RL", "RR"]
# MQTT discovery labels (lowercase ids) + door bitmask bits.
TYRE_POS = (("fl", "Front left"), ("fr", "Front right"), ("rl", "Rear left"), ("rr", "Rear right"))
DOOR_BITS = (
    ("door_driver", "Driver door", 1),
    ("door_passenger", "Passenger door", 2),
    ("door_rear_left", "Rear left door", 4),
    ("door_rear_right", "Rear right door", 8),
)

# ---------------------------------------------------------------------------
# vehicleControlConfig → our capability keys (ApiClient.control_caps)
# ---------------------------------------------------------------------------
# Seat: our key → (A/C feature flag, A/C level list)
SEAT_CAPS = (
    ("heatL", "DriverHeater", "LeftHeaterList"),
    ("ventL", "DriverVent", "LeftVentList"),
    ("heatR", "AssistantHeater", "RightHeaterList"),
    ("ventR", "AssistantVent", "RightVentList"),
    ("heatLR", "RearHeater", "RearHeaterList"),
    ("ventLR", "RearVent", "RearVentList"),
    ("heatRR", "RearHeater", "RearHeaterList"),
    ("ventRR", "RearVent", "RearVentList"),
)
CFG_BOOLS = (
    ("lock", "Lock"),
    ("engine", "Engine"),
    ("liftgate", "PowerLiftgate"),
    ("trunk", "Trunk"),
    ("find", "Search"),
    ("charging", "ChargingManagement"),
    ("windshieldHeat", "FrontWindshieldHeater"),
    ("steerHeat", "SteeringWheelHeater"),
)
WIN_BOOLS = (("open", "WindowsOpen"), ("close", "WindowsClose"), ("vent", "WindowsVent"))
ROOF_BOOLS = (("open", "Sunroof"), ("tilt", "SunroofTilting"))
AC_BOOLS = (
    ("switch", "Switch"),
    ("temp", "SetTemperature"),
    ("rapidCool", "RapidCool"),
    ("rapidHeat", "RapidHeat"),
    ("defog", "Defogging"),
    ("purify", "AirPurification"),
)

# ---------------------------------------------------------------------------
# J5 / Indonesia fallbacks (config.json and KNOWN_CAR_OVERRIDES win when set)
# ---------------------------------------------------------------------------
DEFAULT_BATTERY_KWH = 58.9
DEFAULT_WLTP_KWH_100 = 14.8
DEFAULT_TPMS_SCALE = 1.373
DEFAULT_CURRENCY = {"symbol": "Rp", "locale": "id-ID", "code": "IDR"}
DEFAULT_CHEMISTRY = "lfp"
BALANCE_DAYS_LFP = 7
BALANCE_DAYS_NMC = 90
DEFAULT_TARIFF = 2540
DEFAULT_PETROL_KML = 12.0
DEFAULT_PETROL_PRICE = 16250.0
CHG_EFF_AVG = 0.89
CONS_NORMAL_MAX = 18          # kWh/100km: below = normal, at/above = "boros"
KPA_TO_PSI = 0.145038
TYRE_TEMP_SCALE = 0.65
TYRE_TEMP_OFFSET = -40
TYRE_INVALID = 0xFF

# Per-model overrides CarLinko never sends (e.g. pack kWh). Keys are identifying words;
# VehicleState matches model strings word-wise (most specific key wins). Owner-confirmed
# values — add yours: https://github.com/elad-bar/ha-carlinko/issues/new?template=compatibility.md
KNOWN_CAR_OVERRIDES = {
    "jaecoo j5 ev": {"battery_kwh": 58.9, "wltp_kwh_100": 14.8, "chemistry": "lfp"},   # reference (ID)
    "tiggo 8 phev": {"battery_kwh": 18.3, "tpms_scale": 1.779, "powertrain": "phev"},  # issue #1 (ZA)
    "tiggo 7 phev": {"battery_kwh": 18.3, "tpms_scale": 1.779, "powertrain": "phev",
                     "wltp_kwh_100": 19.68},                                           # issue #3 (MY)
    "tiggo 7 csh": {"battery_kwh": 18.3, "tpms_scale": 1.779, "powertrain": "phev",
                    "wltp_kwh_100": 19.68},  # Malaysia badges the same car "TIGGO 7 CSH" (#3)
    "omoda e5": {"battery_kwh": 61, "wltp_kwh_100": 15.5, "chemistry": "lfp"},   # issue #5 (UY)
}

# Empty live-state skeleton for VehicleState (deepcopy before use — nested mutables).
# Blob fields use BLOB key names; scaled/derived values live in *_calculated keys.
EMPTY_VEHICLE_STATE = {
    "vehicle": {"plate": "—", "model": "EV", "vin": "—"},
    "battery_kwh": DEFAULT_BATTERY_KWH,
    "currency": dict(DEFAULT_CURRENCY),
    "tyre_unit": "psi",
    "tariff": None,
    "battery": None,
    "range": None,
    "odo": None,
    "volt12": None,
    "volt12_calculated": None,
    "unlocked": None,
    "speed": None,
    "speed_calculated": None,
    "updated": None,
    "updated_ts": None,
    "online": False,
    "age_min": None,
    "ac_on": False,
    "engine_on": None,
    "doors": None,
    "trunk": None,
    "windows": None,
    "sunroof": None,
    "defrost_front": None,
    "hv_state": None,
    "wltc_range": None,
    "headline_range": None,
    "ac_temp": None,
    "ac_temp_calculated": None,
    "seat_heat_l": None,
    "seat_heat_r": None,
    "seat_vent_l": None,
    "seat_vent_r": None,
    "consumption": None,
    "consumption_calculated": None,
    "fuel_pct": None,
    "fuel_l_100": None,
    "fuel_l_100_calculated": None,
    "charge_mode": None,
    "charge_state": None,
    "charge_remain": None,
    "charge_remain_calculated": None,
    "charge_power": None,
    "charge_power_calculated": None,
    "tyre_indirect": True,
    "tyre_status": "Normal",
    "tpms": [{"pos": p, "psi": None, "temp": None, "valid": False} for p in TPMS_POS],
    "moving": False,
    "powertrain": "bev",
    "fuel": None,
    "charging": {
        "active": False,
        "mode": "none",
        "state": None,
        "remaining_min": None,
        "rate_kw": 0,
    },
    "volt12_status": "",
}

# ---------------------------------------------------------------------------
# Analytics / session thresholds (server)
# ---------------------------------------------------------------------------
SESSION_TTL = 30 * 86400
IDLE_GAP = 1800               # parked + no SoC rise for 30 min => charge session ended
CHARGE_PARK_MIN = 600         # real charge sits odo-flat >=10 min
MIN_GAIN_PCT = 2              # net SoC gain floor
TRIP_GAP = 180                # parked >3 min => a trip ends
MAX_PAIR_GAP = 1800           # >30 min between frames = logging hole
ODO_MAX_KMH = 160
ODO_RESYNC_KM = 12
CHG_KW_AVG = 55               # fallback DC power when station kW unknown
CAR_DC_CAP = 68               # J5 real-world DC ceiling (avg)

# ---------------------------------------------------------------------------
# Stream defaults (config.json can override stream_backstop)
# ---------------------------------------------------------------------------
POLL_ACTIVE = 5
POLL_PARK = 30
POLL_OFFLINE = 900
HOLD = 600
OFFLINE_AFTER = 3
CHG_LOOKBACK = 900
HEARTBEAT = 5
STREAM_BACKSTOP = 20
TOUCH = 30
RECONNECT_WAIT = 3

# ---------------------------------------------------------------------------
# Static tables (server)
# ---------------------------------------------------------------------------
KNOWN_OPCODES = [
    {"code": "2301", "note": "captured (returned 50043 while the car was asleep)"},
    {"code": "24", "note": "captured"},
    {"code": "77", "note": "captured"},
]

PUBLIC_PATHS = frozenset({
    "/login.html", "/icon.svg", "/manifest.webmanifest",
    "/api/status", "/api/login", "/api/unlock",
})

_TIGGO7_SPECS = {
    "label": "Chery Tiggo 7 PHEV", "source": "owner-reported, issue #3",
    "performance": [["Power", 279, "PS"], ["Torque", 365, "Nm"], ["Battery", 18.3, "kWh"]],
    "dimensions": [["Length", 4553, "mm"]],
    "notes": ["owner_reported"],
}

MODEL_SPECS = {
    "jaecoo j5 ev": {
        "label": "Jaecoo J5 EV", "source": "Andalan Motors",
        "performance": [["Power", 210, "PS"], ["Torque", 288, "Nm"], ["0-100 km/h", 7.3, "s"],
                        ["DC 10-80%", 28, "min"], ["Battery", 60.9, "kWh"],
                        ["Range NEDC", 461, "km"], ["Drivetrain", "FWD", ""]],
        "dimensions": [["Length", 4380, "mm"], ["Width", 1860, "mm"], ["Height", 1650, "mm"],
                       ["Wheelbase", 2620, "mm"], ["Ground clearance", 200, "mm"]],
        "notes": ["gross_vs_usable", "nedc_optimistic"],
    },
    "tiggo 7 phev": _TIGGO7_SPECS,
    "tiggo 7 csh": _TIGGO7_SPECS,
}
