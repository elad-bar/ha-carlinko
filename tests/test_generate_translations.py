"""Merge behaviour for scripts/generate_translations.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN_PATH = ROOT / "scripts" / "generate_translations.py"


def _load_gen():
    spec = importlib.util.spec_from_file_location("generate_translations", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_merge_preserves_existing_strings() -> None:
    gen = _load_gen()
    en = {
        "entity": {
            "sensor": {
                "battery": {"name": "Battery"},
                "range": {"name": "Range"},
            }
        }
    }
    existing = {
        "entity": {
            "sensor": {
                "battery": {"name": "סוללה"},
            }
        }
    }
    mapping = {"Range": "טווח"}
    merged = gen.merge_with_mapping(en, existing, mapping, force=False)
    assert merged["entity"]["sensor"]["battery"]["name"] == "סוללה"
    assert merged["entity"]["sensor"]["range"]["name"] == "טווח"


def test_merge_force_overwrites_existing() -> None:
    gen = _load_gen()
    en = {"entity": {"sensor": {"battery": {"name": "Battery"}}}}
    existing = {"entity": {"sensor": {"battery": {"name": "סוללה"}}}}
    mapping = {"Battery": "מצבר"}
    merged = gen.merge_with_mapping(en, existing, mapping, force=True)
    assert merged["entity"]["sensor"]["battery"]["name"] == "מצבר"


def test_collect_missing_skips_filled_leaves() -> None:
    gen = _load_gen()
    en = {
        "a": "One",
        "b": "Two",
    }
    existing = {"a": "Translated"}
    missing: list[str] = []
    gen.collect_missing_english(en, existing, missing)
    assert missing == ["Two"]
