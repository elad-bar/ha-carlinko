"""Fix CarLinko brand and {error} placeholders in generated locale JSON."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANS = ROOT / "custom_components" / "carlinko" / "translations"


def fix_control_failed(msg: str) -> str:
    if "{error}" in msg:
        return msg
    for sep in (": ", ":", "\uff1a"):
        if sep in msg:
            prefix = msg.rsplit(sep, 1)[0]
            if sep == "\uff1a":
                return f"{prefix}\uff1a{{error}}"
            return f"{prefix}: {{error}}"
    return msg.replace("ERRORPH", "{error}")


def main() -> None:
    for path in sorted(TRANS.glob("*.json")):
        if path.name == "en.json":
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("CARLINKO", "CarLinko")
        data = json.loads(text)
        cf = data["exceptions"]["control_failed"]["message"]
        data["exceptions"]["control_failed"]["message"] = fix_control_failed(
            cf.replace("ERRORPH", "{error}")
        )
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
