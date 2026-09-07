"""Engine seat-probe blob snapshot diffs (HA-free)."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

_ENGINE = Path(__file__).resolve().parents[1] / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

import entrypoint as engine  # noqa: E402
import ha_free_path  # noqa: E402, F401


def _blob(**set_bytes: int) -> str:
    raw = bytearray(72)
    raw[0] = 0x77
    raw[1] = 0x00
    for idx, val in set_bytes.items():
        raw[int(idx)] = val
    return raw.hex()


def test_status_blob_map_is_unique_and_non_overlapping() -> None:
    keys = [row.key for row in engine.STATUS_BLOB_MAP]
    assert len(keys) == len(set(keys))
    covered: set[int] = set()
    last_start = -1
    for row in engine.STATUS_BLOB_MAP:
        assert row.raw_end > row.raw_start
        assert row.raw_start >= last_start
        chunk = set(range(row.raw_start, row.raw_end))
        assert not (chunk & covered)
        covered |= chunk
        last_start = row.raw_start


def test_seat_probe_baseline_and_named_delta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="entrypoint")
    probe = engine.SeatProbe()
    probe.observe(_blob())
    assert "seat probe baseline" in caplog.text
    assert "seat_heat_A=0" in caplog.text
    assert "soc=0" in caplog.text
    caplog.clear()
    probe.observe(_blob())
    assert caplog.text == ""
    probe.observe(_blob(**{"34": 2}))
    assert "seat_heat_B 0→2" in caplog.text
    assert "soc" not in caplog.text


def test_seat_probe_logs_any_mapped_key_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="entrypoint")
    probe = engine.SeatProbe()
    probe.observe(_blob(**{"28": 50}))
    caplog.clear()
    probe.observe(_blob(**{"28": 51}))
    assert "soc 50→51" in caplog.text


def test_seat_probe_logs_unmapped_raw_byte(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="entrypoint")
    probe = engine.SeatProbe()
    probe.observe(_blob())
    caplog.clear()
    probe.observe(_blob(**{"1": 7}))
    assert "raw[1] 0→7" in caplog.text


def test_parse_args_seat_probe_exclusive() -> None:
    args = engine._parse_args(["--seat-probe"])
    assert args.seat_probe is True
    assert args.locate is False
    with pytest.raises(SystemExit):
        engine._parse_args(["--locate", "--seat-probe"])


def test_parse_args_seat_test() -> None:
    args = engine._parse_args(["--seat-test", "vent-rr", "--delay", "0"])
    assert args.seat_test == "vent-rr"
    assert args.delay == 0.0
    with pytest.raises(SystemExit):
        engine._parse_args(["--seat-probe", "--seat-test", "vent-rr"])


def test_climate_ready() -> None:
    assert engine._climate_ready({"ac_switch": 1, "engine": 0}) is True
    assert engine._climate_ready({"ac_switch": 0, "engine": 2}) is True
    assert engine._climate_ready({"ac_switch": 0, "engine": 0}) is False


def test_confirm_seat_on_one_key() -> None:
    before = dict.fromkeys(engine._VENT_KEYS, 0)
    after = dict(before)
    after["seat_vent_D"] = 2
    assert engine._confirm_seat_on(before, after, engine._VENT_KEYS) == "seat_vent_D"
    after["seat_vent_B"] = 2
    assert engine._confirm_seat_on(before, after, engine._VENT_KEYS) is None


@pytest.mark.asyncio
async def test_run_seat_test_vent_rr(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="entrypoint")
    probe = engine.SeatProbe()
    probe.observe(_blob())

    class _Api:
        async def send_control(self, opcode, timeout=20, **kwargs):
            if opcode == engine._AC_ON:
                probe.observe(_blob(**{"5": 2, "23": 1}))
            elif opcode == "741E02":
                probe.observe(_blob(**{"5": 2, "23": 1, "41": 2}))
            elif opcode == "741E00":
                probe.observe(_blob(**{"5": 2, "23": 1}))
            elif opcode == engine._AC_OFF:
                probe.observe(_blob())
            return {"code": "0000"}

    rc = await engine.async_run_seat_test(
        probe, _Api(), "veh-1", "vent-rr", delay_s=0, timeout_s=2
    )
    assert rc == 0
    assert "blob_key=seat_vent_D" in caplog.text
