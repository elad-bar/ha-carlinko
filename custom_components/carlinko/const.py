"""Constants for the CarLinko Home Assistant integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "carlinko"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"

# Entity considered unavailable when last frame older than this (legacy ~40 min).
AVAILABILITY_SECONDS = 2400

CAPS_REFRESH_INTERVAL_S = 3300

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.LOCK,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.store"
