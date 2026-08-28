#!/usr/bin/env python3
"""Fill missing HA locale strings from en.json (preserves existing translations)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
EN_PATH = ROOT / "custom_components" / "carlinko" / "translations" / "en.json"
OUT_DIR = EN_PATH.parent

LOCALES: dict[str, str] = {
    "ar": "ar",
    "es": "es",
    "fa": "fa",
    "fr": "fr",
    "he": "iw",
    "id": "id",
    "kk": "kk",
    "ms": "ms",
    "pt": "pt",
    "ru": "ru",
    "th": "th",
    "vi": "vi",
    "zh-Hans": "zh-CN",
    "zh-Hant": "zh-TW",
}

PROTECTED = (
    ("CarLinko", "§§CARLINKO§§"),
    ("{error}", "§§ERROR§§"),
)

TECHNICAL = frozenset({"AC", "DC", "LV", "OK", "12V"})


def protect(text: str) -> str:
    for orig, tok in PROTECTED:
        text = text.replace(orig, tok)
    return text


def restore(text: str) -> str:
    for orig, tok in PROTECTED:
        text = text.replace(tok, orig)
    return text


def get_subtree(node: Any, key: str) -> Any:
    if not isinstance(node, dict):
        return None
    return node.get(key)


def collect_missing_english(
    en_node: Any,
    existing_node: Any,
    missing: list[str],
) -> None:
    """Append English leaf values that have no string yet in existing_node at same path."""
    if isinstance(en_node, dict):
        existing_dict = existing_node if isinstance(existing_node, dict) else {}
        for key, en_child in en_node.items():
            collect_missing_english(
                en_child,
                get_subtree(existing_dict, key),
                missing,
            )
        return
    if isinstance(en_node, str):
        if isinstance(existing_node, str) and existing_node.strip():
            return
        missing.append(en_node)


def merge_with_mapping(
    en_node: Any,
    existing_node: Any,
    mapping: dict[str, str],
    *,
    force: bool,
) -> Any:
    if isinstance(en_node, dict):
        existing_dict = existing_node if isinstance(existing_node, dict) else {}
        return {
            key: merge_with_mapping(
                en_child,
                get_subtree(existing_dict, key),
                mapping,
                force=force,
            )
            for key, en_child in en_node.items()
        }
    if isinstance(en_node, str):
        if (
            not force
            and isinstance(existing_node, str)
            and existing_node.strip()
        ):
            return existing_node
        return mapping.get(en_node, en_node)
    raise TypeError(f"unexpected node type: {type(en_node)}")


def build_mapping(values: list[str], google_code: str) -> dict[str, str]:
    translator = GoogleTranslator(source="en", target=google_code)
    mapping: dict[str, str] = {}
    batch: list[str] = []
    batch_src: list[str] = []

    def flush() -> None:
        nonlocal batch, batch_src
        if not batch:
            return
        try:
            translated = translator.translate_batch(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"  batch failed {exc!r}, falling back per-string", file=sys.stderr)
            translated = []
            for item in batch:
                try:
                    translated.append(translator.translate(item))
                except Exception as exc2:  # noqa: BLE001
                    print(f"  warn: {exc2!r}", file=sys.stderr)
                    translated.append(item)
                time.sleep(0.05)
        for src, tgt in zip(batch_src, translated):
            mapping[src] = restore(tgt) if tgt else src
        batch = []
        batch_src = []
        time.sleep(0.2)

    for src in values:
        if src in mapping:
            continue
        if src in TECHNICAL or not src.strip():
            mapping[src] = src
            continue
        protected = protect(src)
        batch.append(protected)
        batch_src.append(src)
        if len(batch) >= 40:
            flush()
    flush()
    return mapping


def count_preserved(en_node: Any, existing_node: Any, merged_node: Any) -> tuple[int, int]:
    """Return (preserved, translated) leaf counts."""
    if isinstance(en_node, dict):
        preserved = translated = 0
        existing_dict = existing_node if isinstance(existing_node, dict) else {}
        merged_dict = merged_node if isinstance(merged_node, dict) else {}
        for key, en_child in en_node.items():
            p, t = count_preserved(
                en_child,
                get_subtree(existing_dict, key),
                get_subtree(merged_dict, key),
            )
            preserved += p
            translated += t
        return preserved, translated
    if isinstance(en_node, str):
        if (
            isinstance(existing_node, str)
            and existing_node.strip()
            and existing_node == merged_node
        ):
            return 1, 0
        return 0, 1
    return 0, 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate missing CarLinko HA locale strings from en.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate every string (overwrites manual edits).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))

    for filename, google_code in LOCALES.items():
        out_path = OUT_DIR / f"{filename}.json"
        existing: Any = {}
        if out_path.is_file():
            existing = json.loads(out_path.read_text(encoding="utf-8"))

        missing: list[str] = []
        if args.force:
            collect_missing_english(en, {}, missing)
        else:
            collect_missing_english(en, existing, missing)
        unique_missing = list(dict.fromkeys(missing))

        print(
            f"{out_path.name} ({google_code}): "
            f"{len(unique_missing)} new/changed strings to translate"
        )
        if not unique_missing:
            merged = merge_with_mapping(en, existing, {}, force=False)
            out_path.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            continue

        mapping = build_mapping(unique_missing, google_code)
        merged = merge_with_mapping(en, existing, mapping, force=args.force)
        preserved, translated = count_preserved(en, existing, merged)
        print(f"  preserved {preserved}, machine-translated {translated}")
        out_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
