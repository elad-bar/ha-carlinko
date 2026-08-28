#!/usr/bin/env python3
"""Print the Keep a Changelog section for a given semver (for GitHub Releases)."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"

SECTION_HEADER = re.compile(r"^## \[([^\]]+)\]")


def extract_changelog_section(text: str, version: str) -> str:
    """Return markdown body for ``version`` (content under ``## [version]``)."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        match = SECTION_HEADER.match(line)
        if match and match.group(1) == version:
            start = i + 1
            break
    if start is None:
        raise ValueError(f"No changelog section for version {version!r}")

    end = len(lines)
    for j in range(start, len(lines)):
        if SECTION_HEADER.match(lines[j]):
            end = j
            break

    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise ValueError(f"Changelog section for {version!r} is empty")
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Semver from manifest.json (e.g. 0.1.1)")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help=f"Path to CHANGELOG.md (default: {DEFAULT_CHANGELOG})",
    )
    args = parser.parse_args()
    text = args.changelog.read_text(encoding="utf-8")
    try:
        section = extract_changelog_section(text, args.version)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
