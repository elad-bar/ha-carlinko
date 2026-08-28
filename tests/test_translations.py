"""Translation JSON key parity with en.json."""

from __future__ import annotations

import json
from pathlib import Path

TRANSLATIONS_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "carlinko"
    / "translations"
)


def leaf_key_paths(node: object, prefix: str = "") -> set[str]:
    """Return dotted paths to string leaf values."""
    if isinstance(node, dict):
        paths: set[str] = set()
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            paths |= leaf_key_paths(value, child)
        return paths
    if isinstance(node, str):
        return {prefix}
    raise TypeError(f"unexpected node at {prefix!r}: {type(node)}")


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_translation_files_match_en_keys() -> None:
    en_path = TRANSLATIONS_DIR / "en.json"
    en_data = load_json(en_path)
    en_keys = leaf_key_paths(en_data)

    locale_files = sorted(
        p for p in TRANSLATIONS_DIR.glob("*.json") if p.name != "en.json"
    )
    assert locale_files, "expected at least one non-English locale file"

    for path in locale_files:
        data = load_json(path)
        keys = leaf_key_paths(data)
        missing = en_keys - keys
        extra = keys - en_keys
        assert not missing, f"{path.name} missing keys: {sorted(missing)[:5]}"
        assert not extra, f"{path.name} extra keys: {sorted(extra)[:5]}"


def test_translation_string_leaves_non_empty() -> None:
    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        data = load_json(path)

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, str):
                assert node.strip(), f"{path.name} has empty string leaf"
            else:
                raise TypeError(f"{path.name}: unexpected {type(node)}")

        walk(data)


def test_control_failed_preserves_error_placeholder() -> None:
    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        data = load_json(path)
        message = data["exceptions"]["control_failed"]["message"]
        assert "{error}" in message, f"{path.name} control_failed missing {{error}}"
