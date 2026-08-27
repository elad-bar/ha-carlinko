"""One-shot logging configuration for the engine process."""
from __future__ import annotations

import logging
import os
import sys


def _resolve_level() -> int:
    raw = (os.environ.get("CARLINKO_LOG_LEVEL") or "").strip().upper()
    if raw:
        return getattr(logging, raw, logging.INFO)
    debug = str(os.environ.get("DEBUG", "")).lower() == "true"
    return logging.DEBUG if debug else logging.INFO


def configure_logging() -> None:
    level = _resolve_level()
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
