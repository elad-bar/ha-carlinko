"""CarLinko WS stream → live entity change logs (dev harness; no HA).

Requires .env (CARLINKO_EMAIL / PASSWORD / REGION) and data/config.json
(same CarlinkoStore as HA, file-backed). HA-free code lives in
custom_components/carlinko/{managers,models}/.

Usage:
  python entrypoint.py
  python entrypoint.py --locate
  python entrypoint.py --seat-probe
  python entrypoint.py --seat-test vent-rr
"""

from __future__ import annotations

import ha_free_path  # noqa: F401  # isort: skip  # mount carlinko before HA-free imports

import argparse
import asyncio
import logging
import os
import signal
import socket
import ssl
import sys
import time
from typing import Any, Callable, NamedTuple

import aiohttp
from carlinko.common.consts import OK_CODE, USER_AGENT
from carlinko.common.helpers import partial_id
from carlinko.managers.api_client import ApiClient, meta_from_api_row, vehicle_id_of
from carlinko.managers.store import CarlinkoStore
from carlinko.managers.ws_client import WsClient
from carlinko.models.entity_specs import ENTITY_SPECS, get_entity_specs
from carlinko.models.entity_values import EntityValueResolver
from carlinko.models.vehicle_state import VehicleState
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

load_dotenv(os.path.join(REPO, ".env"))

_CAPS_REFRESH_INTERVAL_S = 3300
_LOGGER = logging.getLogger(__name__)


class StatusBlobField(NamedTuple):
    """One row of the app status map. Indexes are on the full ``7700`` buffer."""

    key: str
    raw_start: int
    raw_end: int
    meaning: str


# App ``sublist(2)`` drops ``77 00``; raw_idx = app_idx + 2. Not the HA decoder.
STATUS_BLOB_MAP: tuple[StatusBlobField, ...] = (
    StatusBlobField("lock", 3, 4, "door lock"),
    StatusBlobField("trunk", 4, 5, "trunk open"),
    StatusBlobField("engine", 5, 6, "hv_state (app engine icon)"),
    StatusBlobField("window", 8, 9, "window state"),
    StatusBlobField("sunroof", 9, 10, "sunroof"),
    StatusBlobField("window_mode", 11, 12, "window decode mode"),
    StatusBlobField("unknown_u16_a", 12, 14, "volt12 BE u16 x0.01 (app x0.1 label)"),
    StatusBlobField("packed_mileage", 18, 21, "BE 24-bit mileage"),
    StatusBlobField("fuel_pct", 21, 22, "fuel percent"),
    StatusBlobField("ac_switch", 23, 24, "ac on/off"),
    StatusBlobField("ac_temp", 24, 25, "ac set temp"),
    StatusBlobField("soc", 28, 29, "battery soc"),
    StatusBlobField("electric_mileage", 29, 31, "BE u16 ev range"),
    StatusBlobField("seat_heat_A", 32, 33, "front L heat (dash-confirmed)"),
    StatusBlobField("seat_heat_C", 33, 34, "front R heat (dash-confirmed)"),
    StatusBlobField("seat_heat_B", 34, 35, "rear L heat (7417 live-confirmed)"),
    StatusBlobField("unconfirmed_35", 35, 36, "unread by listed parsers"),
    StatusBlobField("seat_heat_D", 36, 37, "rear R heat (dash-confirmed)"),
    StatusBlobField("seat_vent_A", 37, 38, "front L vent (dash-confirmed)"),
    StatusBlobField("seat_vent_C", 38, 39, "front R vent (dash-confirmed)"),
    StatusBlobField("seat_vent_B", 39, 40, "rear L vent (inferred vs D=RR)"),
    StatusBlobField("unconfirmed_40", 40, 41, "unread by listed parsers"),
    StatusBlobField("seat_vent_D", 41, 42, "rear R vent (741E live-confirmed)"),
    StatusBlobField("front_defog", 42, 43, "front defog"),
    StatusBlobField("unknown_u16_b", 52, 54, "BE u16 x0.1 unknown"),
    StatusBlobField("packed_u16", 54, 56, "BE packed u16"),
    StatusBlobField("charge_icon_mode", 56, 57, "charge icon"),
    StatusBlobField("charge_status_val", 57, 58, "charge status"),
    StatusBlobField("charge_remain_time", 58, 60, "BE u16 remain min"),
    StatusBlobField("ac_heating", 60, 61, "quick heat"),
    StatusBlobField("ac_cooling", 61, 62, "quick cool"),
    StatusBlobField("charge_power", 62, 64, "BE u16 x0.1 kW"),
    StatusBlobField("heat_accessory_A", 64, 65, "windshield heat (dash-confirmed)"),
    StatusBlobField("heat_accessory_B", 65, 66, "steering wheel heat (dash-confirmed)"),
    StatusBlobField("air_purify", 66, 67, "air purify"),
    StatusBlobField("high_low_gear", 67, 68, "high/low gear"),
    StatusBlobField("wltc_mileage", 68, 70, "BE u16 wltc range"),
    StatusBlobField("alt_mileage", 70, 72, "BE u16 second range"),
)

_PROBE_COVERED = frozenset(
    idx for row in STATUS_BLOB_MAP for idx in range(row.raw_start, row.raw_end)
)
_PROBE_NAMES = tuple(row.key for row in STATUS_BLOB_MAP)

_AC_ON = "741001"
_AC_OFF = "741000"
_HEAT_KEYS = ("seat_heat_A", "seat_heat_C", "seat_heat_B", "seat_heat_D")
_VENT_KEYS = ("seat_vent_A", "seat_vent_C", "seat_vent_B", "seat_vent_D")


class SeatTestTarget(NamedTuple):
    """One --seat-test id: on/off opcodes and which blob family to watch."""

    on_opcode: str
    off_opcode: str
    family: tuple[str, ...]


SEAT_TEST_TARGETS: dict[str, SeatTestTarget] = {
    "heat-l": SeatTestTarget("741502", "741500", _HEAT_KEYS),
    "heat-r": SeatTestTarget("741602", "741600", _HEAT_KEYS),
    "heat-lr": SeatTestTarget("741702", "741700", _HEAT_KEYS),
    "heat-rr": SeatTestTarget("741902", "741900", _HEAT_KEYS),
    "vent-l": SeatTestTarget("741A02", "741A00", _VENT_KEYS),
    "vent-r": SeatTestTarget("741B02", "741B00", _VENT_KEYS),
    "vent-lr": SeatTestTarget("741C02", "741C00", _VENT_KEYS),
    "vent-rr": SeatTestTarget("741E02", "741E00", _VENT_KEYS),
}


def _ssl_context() -> ssl.SSLContext:
    """Default verify, but drop VERIFY_X509_STRICT (Py3.13+ / OpenSSL).

    CarLinko API intermediates can lack Authority Key Identifier; strict mode
    then fails handshake even though the chain is otherwise valid.
    """
    ctx = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def _connector() -> aiohttp.TCPConnector:
    return aiohttp.TCPConnector(family=socket.AF_INET, ssl=_ssl_context())


def _configure_logging() -> None:
    raw = (os.environ.get("CARLINKO_LOG_LEVEL") or "").strip().upper()
    if raw:
        level = getattr(logging, raw, logging.INFO)
    else:
        debug = str(os.environ.get("DEBUG", "")).lower() == "true"
        level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(threadName)s[%(thread)d] %(levelname)s %(name)s %(message)s"
        )
    )
    root.addHandler(handler)
    for name in ("aiohttp", "aiohttp.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


class EntityPublisher:
    """Dev-only: resolve EntitySpecs → INFO logs on value change."""

    def __init__(self, store: CarlinkoStore, get_caps: Callable[[], dict]):
        self.store = store
        self.get_caps = get_caps
        self._resolver = EntityValueResolver(store)
        self._last: dict[str, Any] = {}

    def publish(self, state: dict) -> None:
        try:
            caps = self.get_caps() or {}
        except Exception:
            caps = {}
        state = state or {}
        specs = get_entity_specs(state=state, caps=caps)
        active = set()
        for spec in specs:
            active.add(spec.key)
            if not spec.has_live_state():
                continue
            value = self._resolver.resolve_value(spec, state)
            if spec.key not in self._last or self._last[spec.key] != value:
                old = (
                    "—"
                    if spec.key not in self._last
                    else spec.format_value(self._last[spec.key])
                )
                _LOGGER.info(
                    "%s: %s → %s",
                    spec.name,
                    old,
                    spec.format_value(value),
                )
                self._last[spec.key] = value
        for key in list(self._last):
            if key not in active:
                del self._last[key]

    def log_command(self, key: str, action: str | None = None) -> None:
        spec = next((s for s in ENTITY_SPECS if s.key == key), None)
        if not spec:
            _LOGGER.info("command %s %s", key, action)
            return
        if action is None and spec.platform == "button":
            action = "press"
        _LOGGER.info("%s", spec.format_command(action))


def _read_row(blob: bytes, row: StatusBlobField) -> int | None:
    if len(blob) < row.raw_end:
        return None
    if row.raw_end - row.raw_start == 1:
        return blob[row.raw_start]
    return int.from_bytes(blob[row.raw_start : row.raw_end], "big")


def _probe_snapshot(blob: bytes) -> dict[str, int | None]:
    snap: dict[str, int | None] = {}
    for row in STATUS_BLOB_MAP:
        snap[row.key] = _read_row(blob, row)
    for idx, val in enumerate(blob):
        if idx in _PROBE_COVERED:
            continue
        snap[f"raw[{idx}]"] = val
    return snap


def _probe_diff(prev: dict[str, int | None], snap: dict[str, int | None]) -> list[str]:
    changes = []
    for name in _PROBE_NAMES:
        old, new = prev.get(name), snap.get(name)
        if old != new:
            changes.append(f"{name} {old}→{new}")
    raw_keys = sorted(
        (k for k in set(prev) | set(snap) if k.startswith("raw[")),
        key=lambda k: int(k[4:-1]),
    )
    for key in raw_keys:
        old, new = prev.get(key), snap.get(key)
        if old != new:
            changes.append(f"{key} {old}→{new}")
    return changes


def _climate_ready(snap: dict[str, int | None] | None) -> bool:
    if not snap:
        return False
    ac = snap.get("ac_switch")
    hv = snap.get("engine")
    return ac == 1 or (hv is not None and int(hv) >= 2)


def _confirm_seat_on(
    before: dict[str, int | None],
    after: dict[str, int | None],
    family: tuple[str, ...],
) -> str | None:
    """Return the single family key that went to a positive level, else None."""
    changed = [k for k in family if before.get(k) != after.get(k)]
    if len(changed) != 1:
        return None
    key = changed[0]
    new = after.get(key)
    try:
        level = int(new) if new is not None else 0
    except (TypeError, ValueError):
        return None
    if level <= 0:
        return None
    return key


def _opcode_ok(result: dict[str, Any] | None) -> bool:
    code = str((result or {}).get("code") or "")
    return code in (OK_CODE, "0")


class SeatProbe:
    """Snapshot named blob keys each frame; INFO-log only values that changed."""

    def __init__(self) -> None:
        self._last: dict[str, int | None] | None = None
        self._gen = 0
        self._event = asyncio.Event()

    @property
    def snap(self) -> dict[str, int | None] | None:
        return self._last

    def observe(self, hexstr: str) -> None:
        try:
            blob = bytes.fromhex(str(hexstr).strip())
        except ValueError:
            _LOGGER.warning(f"seat probe invalid hex n={len(str(hexstr))}")
            return
        snap = _probe_snapshot(blob)
        if self._last is None:
            parts = " ".join(f"{name}={snap.get(name)}" for name in _PROBE_NAMES)
            _LOGGER.info(f"seat probe baseline {parts}")
            self._last = snap
            self._gen += 1
            self._event.set()
            return
        changes = _probe_diff(self._last, snap)
        self._last = snap
        self._gen += 1
        self._event.set()
        if not changes:
            return
        _LOGGER.info(f"seat probe delta {' '.join(changes)}")

    async def wait_until(
        self, pred: Callable[[dict[str, int | None]], bool], timeout: float
    ) -> dict[str, int | None] | None:
        deadline = time.monotonic() + timeout
        seen = self._gen
        while True:
            snap = self._last
            if snap is not None and pred(snap):
                return snap
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if self._gen != seen:
                seen = self._gen
                continue
            self._event.clear()
            if self._gen != seen:
                continue
            try:
                await asyncio.wait_for(self._event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            seen = self._gen


class SeatProbeState(VehicleState):
    """VehicleState that also feeds SeatProbe from each raw hex frame."""

    def __init__(self, probe: SeatProbe) -> None:
        super().__init__()
        self._probe = probe

    def update_data(self, hexstr):
        self._probe.observe(hexstr)
        return super().update_data(hexstr)


def _env_secrets():
    email = (os.environ.get("CARLINKO_EMAIL") or "").strip()
    password = os.environ.get("CARLINKO_PASSWORD") or ""
    region = (os.environ.get("CARLINKO_REGION") or "").strip()
    if not email or not password:
        _LOGGER.error(
            "CARLINKO_EMAIL / CARLINKO_PASSWORD missing — copy .env.example → .env"
        )
        sys.exit(2)
    return email, password, region


async def _caps_refresh_loop(
    api: ApiClient, store: CarlinkoStore, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_CAPS_REFRESH_INTERVAL_S)
            return
        except asyncio.TimeoutError:
            pass
        try:
            rows = await api.async_list_vehicles(force=True)
            _sync_store_vehicles(store, rows)
        except Exception:
            _LOGGER.exception("vehicle cache refresh failed")


def _sync_store_vehicles(store: CarlinkoStore, rows: list[dict[str, Any]]) -> None:
    metas: dict[str, dict[str, Any]] = {}
    for row in rows:
        vid = vehicle_id_of(row)
        if not vid:
            continue
        metas[vid] = meta_from_api_row(row)
    store.set_vehicles(metas)


def _resolve_vehicle_id(
    store: CarlinkoStore,
    api: ApiClient,
    preferred: str | None,
) -> str:
    """Pick one car: --vehicle-id, else sole fleet member, else error."""
    want = str(preferred or "").strip()
    store_ids = list(store.get_vehicles())
    api_ids = list(api._veh_by_id)
    known = store_ids or api_ids

    if want:
        if want not in known and want not in api._veh_by_id:
            _LOGGER.error(
                "vehicle_id=%s not in fleet ids=%s — check --vehicle-id / config",
                want,
                known,
            )
            sys.exit(2)
        return want

    if len(known) == 1:
        return known[0]
    if len(api_ids) == 1:
        return api_ids[0]

    _LOGGER.error(
        "multiple vehicles %s — pass --vehicle-id <id>",
        known or api_ids,
    )
    sys.exit(2)


def _register_stop_handlers(
    loop: asyncio.AbstractEventLoop, stop: asyncio.Event
) -> None:
    def request_stop(*_):
        _LOGGER.info("shutting down")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


def _log_locate_result(result: dict[str, Any]) -> int:
    code = str(result.get("code") or "")
    msg = result.get("msg")
    data = result.get("data")
    if code != OK_CODE:
        _LOGGER.error("deviceLocate failed code=%s msg=%s raw=%s", code, msg, result)
        return 1
    if not isinstance(data, dict):
        _LOGGER.error("deviceLocate ok but data missing/invalid: %s", result)
        return 1
    lat, lng = data.get("lat"), data.get("lng")
    address = data.get("address")
    _LOGGER.info(
        "deviceLocate ok lat=%s lng=%s address=%s",
        lat,
        lng,
        address,
    )
    return 0


async def async_locate(vehicle_id: str | None = None) -> int:
    """Login, refresh vehicle ids, one-shot locate, exit."""
    email, password, region = _env_secrets()
    store = CarlinkoStore.for_engine()

    async with aiohttp.ClientSession(
        connector=_connector(),
        headers={"User-Agent": USER_AGENT},
    ) as session:
        api = ApiClient(email, password, region, store, session)
        _LOGGER.info("logging in to CarLinko…")
        await api.login()
        preferred = (
            vehicle_id or str(store.data.get("vehicle_id") or "").strip() or None
        )
        rows = await api.async_list_vehicles(force=True)
        _sync_store_vehicles(store, rows)
        vid = _resolve_vehicle_id(store, api, preferred)
        _, sn = api.ids_for(vid)
        if not sn:
            _LOGGER.error(
                "no device_sn for vehicle_id=%s after vehicle refresh",
                vid,
            )
            return 2
        _LOGGER.info("POST /maps/deviceLocate vehicle=%s sn=%s…", vid, sn)
        result = await api.device_locate(vehicle_id=vid, device_sn=sn)
        return _log_locate_result(result)


async def _send_opcode(
    api: ApiClient, vehicle_id: str, opcode: str
) -> dict[str, Any] | None:
    result = await api.send_control(opcode, vehicle_id=vehicle_id)
    return result if isinstance(result, dict) else None


async def async_run_seat_test(
    probe: SeatProbe,
    api: ApiClient,
    vehicle_id: str,
    target_id: str,
    *,
    delay_s: float,
    timeout_s: float,
) -> int:
    """A/C if needed, send seat L2, confirm one blob key, send off. Returns exit code."""
    spec = SEAT_TEST_TARGETS[target_id]
    first = await probe.wait_until(lambda snap: True, timeout_s)
    if first is None:
        _LOGGER.error("seat test no status blob within timeout")
        return 2

    turned_ac_on = False
    try:
        if not _climate_ready(probe.snap):
            _LOGGER.info("seat test climate down — sending A/C on")
            ac = await _send_opcode(api, vehicle_id, _AC_ON)
            if not _opcode_ok(ac):
                _LOGGER.error("seat test A/C on failed")
                return 2
            turned_ac_on = True
            ready = await probe.wait_until(_climate_ready, timeout_s)
            if ready is None:
                _LOGGER.error("seat test climate did not come up")
                return 2
        else:
            _LOGGER.info("seat test climate already up")

        if delay_s > 0:
            _LOGGER.info(f"seat test delay {delay_s}s before opcode")
            await asyncio.sleep(delay_s)

        before = dict(probe.snap or {})
        _LOGGER.info(f"seat test send on target={target_id} opcode={spec.on_opcode}")
        on_res = await _send_opcode(api, vehicle_id, spec.on_opcode)
        if not _opcode_ok(on_res):
            _LOGGER.error(
                f"seat test on rejected target={target_id} opcode={spec.on_opcode}"
            )
            return 1

        after_on = await probe.wait_until(
            lambda snap: _confirm_seat_on(before, snap, spec.family) is not None,
            timeout_s,
        )
        if after_on is None:
            fam = " ".join(f"{k}={(probe.snap or {}).get(k)}" for k in spec.family)
            _LOGGER.error(f"seat test on not confirmed target={target_id} family={fam}")
            await _send_opcode(api, vehicle_id, spec.off_opcode)
            return 1

        hit = _confirm_seat_on(before, after_on, spec.family)
        _LOGGER.info(
            f"seat test on confirmed target={target_id} blob_key={hit} "
            f"level={after_on.get(hit)}"
        )

        _LOGGER.info(f"seat test send off target={target_id} opcode={spec.off_opcode}")
        off_res = await _send_opcode(api, vehicle_id, spec.off_opcode)
        if not _opcode_ok(off_res):
            _LOGGER.error("seat test off rejected")
            return 1

        after_off = await probe.wait_until(
            lambda snap: hit is not None and int(snap.get(hit) or 0) == 0,
            timeout_s,
        )
        if after_off is None:
            _LOGGER.error(f"seat test off not confirmed blob_key={hit}")
            return 1
        _LOGGER.info(f"seat test off confirmed blob_key={hit}")
        return 0
    finally:
        if turned_ac_on:
            _LOGGER.info("seat test restoring A/C off")
            await _send_opcode(api, vehicle_id, _AC_OFF)


async def async_seat_test(
    target_id: str,
    vehicle_id: str | None = None,
    *,
    delay_s: float = 10.0,
    timeout_s: float = 30.0,
) -> int:
    """Login, stream WS, run one seat opcode confirm, exit."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    _register_stop_handlers(loop, stop)

    email, password, region = _env_secrets()
    store = CarlinkoStore.for_engine()
    probe = SeatProbe()
    vehicle_state = SeatProbeState(probe)

    async with aiohttp.ClientSession(
        connector=_connector(),
        headers={"User-Agent": USER_AGENT},
    ) as session:
        api = ApiClient(email, password, region, store, session)
        _LOGGER.info("logging in to CarLinko…")
        await api.login()
        preferred = (
            vehicle_id or str(store.data.get("vehicle_id") or "").strip() or None
        )
        rows = await api.async_list_vehicles(force=True)
        _sync_store_vehicles(store, rows)
        vid = _resolve_vehicle_id(store, api, preferred)
        _, sn = api.ids_for(vid)
        if not sn:
            _LOGGER.error(f"no device_sn for vehicle_id={partial_id(vid)}")
            return 2

        ws = WsClient(
            vehicle_state,
            api,
            on_frame=None,
            vehicle_id=vid,
            device_sn=sn,
        )
        vehicle_state.update_metadata(
            {
                **store.data,
                "vehicle": store.get_vehicle(vid),
                "vehicle_id": vid,
                "device_sn": sn,
            }
        )
        _LOGGER.info(
            f"seat test target={target_id} vehicle={partial_id(vid)} "
            f"(A/C if needed, L2, confirm blob, off)"
        )
        ws_task = asyncio.create_task(ws.run(stop))
        try:
            return await async_run_seat_test(
                probe,
                api,
                vid,
                target_id,
                delay_s=delay_s,
                timeout_s=timeout_s,
            )
        finally:
            stop.set()
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass


async def async_main(
    vehicle_id: str | None = None, *, seat_probe: bool = False
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    _register_stop_handlers(loop, stop)

    email, password, region = _env_secrets()
    store = CarlinkoStore.for_engine()
    probe = SeatProbe() if seat_probe else None
    vehicle_state = SeatProbeState(probe) if probe else VehicleState()

    async with aiohttp.ClientSession(
        connector=_connector(),
        headers={"User-Agent": USER_AGENT},
    ) as session:
        api = ApiClient(email, password, region, store, session)

        _LOGGER.info("logging in to CarLinko…")
        await api.login()
        preferred = (
            vehicle_id or str(store.data.get("vehicle_id") or "").strip() or None
        )
        rows = await api.async_list_vehicles(force=True)
        _sync_store_vehicles(store, rows)
        vid = _resolve_vehicle_id(store, api, preferred)
        _, sn = api.ids_for(vid)
        if not sn:
            _LOGGER.error("no device_sn for vehicle_id=%s", vid)
            sys.exit(2)

        on_frame = None
        if not seat_probe:
            entities = EntityPublisher(store, lambda: api.control_caps(vid))
            on_frame = entities.publish
        ws = WsClient(
            vehicle_state,
            api,
            on_frame=on_frame,
            vehicle_id=vid,
            device_sn=sn,
        )

        vehicle_state.update_metadata(
            {
                **store.data,
                "vehicle": store.get_vehicle(vid),
                "vehicle_id": vid,
                "device_sn": sn,
            }
        )
        if seat_probe:
            _LOGGER.info(
                f"streaming CarLinko WS vehicle={partial_id(vid)} "
                f"→ seat heat/vent byte probe (toggle one seat at a time)"
            )
        else:
            _LOGGER.info("streaming CarLinko WS vehicle=%s → entity change logs…", vid)

        refresh_task = asyncio.create_task(_caps_refresh_loop(api, store, stop))
        try:
            await ws.run(stop)
        finally:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CarLinko engine harness")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--locate",
        action="store_true",
        help="one-shot POST /maps/deviceLocate probe (no WS stream)",
    )
    mode.add_argument(
        "--seat-probe",
        action="store_true",
        help="WS: log STATUS_BLOB_MAP keys when they change",
    )
    mode.add_argument(
        "--seat-test",
        choices=sorted(SEAT_TEST_TARGETS),
        metavar="SEAT",
        help="send L2 then off for one seat; confirm which blob key moves",
    )
    p.add_argument(
        "--vehicle-id",
        default=None,
        help="CarLinko vehicle id (required when the account has multiple cars)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=10.0,
        help="seconds to wait after climate is up before the seat on opcode",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="seconds to wait for a matching status blob after each command",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    args = _parse_args(argv)
    if args.locate:
        raise SystemExit(asyncio.run(async_locate(args.vehicle_id)))
    if args.seat_test:
        raise SystemExit(
            asyncio.run(
                async_seat_test(
                    args.seat_test,
                    args.vehicle_id,
                    delay_s=args.delay,
                    timeout_s=args.timeout,
                )
            )
        )
    asyncio.run(async_main(args.vehicle_id, seat_probe=args.seat_probe))


if __name__ == "__main__":
    main()
