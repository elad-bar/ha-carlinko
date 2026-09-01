# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.6] - 2026-09-01

### Changed

- **ApiClient** HTTP layer refactored: shared private `_get` / `_post` and auth-retry helpers replace nested per-endpoint request closures; public API unchanged
- **Multi-vehicle IDs:** removed global `ApiClient.vehicle_id` / `device_sn` and store top-level mirrors; `vehicles[<id>].device_sn` is the only source of truth; control / locate / WS require an explicit vehicle
- **SN from fleet list:** read `/user/vehicle`.`deviceId` (not `deviceSn`); empty refresh no longer wipes a stored SN

### Fixed

- Empty `device_sn` in storage when the API returns `deviceId` only (broke locate / remoteControl / firmware for those accounts)

## [0.1.5] - 2026-08-31

### Added

- **Device tracker** (`location`) via `POST /maps/deviceLocate`: capability probed once at setup (`50049` = unsupported; `50052` = supported but no fix yet), then refreshed every 15 minutes when online; upgrades pick up the entity after reload
- **Operational notices** (types vehicle/control): poll every 5 minutes, `notice_unread` sensor, `carlinko_notice` bus event for new rows, and `carlinko.get_notices` service (marketing/CMS inboxes ignored)
- **Service history**: summary sensors (last/next service date and odometer, last project) refreshed every 12 hours; `carlinko.get_maintain_history` / `carlinko.get_maintain_details` for on-demand lists
- **Firmware status** (read-only): check at startup and every 24 hours plus `carlinko.check_firmware`; exposes update-available / offered version / upgrading — does not download or start OTA

## [0.1.4] - 2026-08-31

### Changed

- Removed the **Updated** timestamp sensor; last refresh time remains in vehicle state (`updated`, `updated_ts`) and in diagnostics export (`last_update_ts`, `live_state`) without a dedicated entity that updated every telemetry frame
- Logging overhauled to match [docs/logging.md](docs/logging.md): config-flow and reauth failures log at **warning**; setup, reload, unload, fleet, and capability changes log **info** milestones; auth failures include **source** and **starting reauth flow** at **error**; remote control and local cost-number actions log at the entity layer. Recommended day-to-day: `custom_components.carlinko: info`; use **debug** for path tracing or **warning** for problems-only tails
- **Reconfigure** removed from the integration menu; update credentials via **Re-authenticate** when prompted. **Region** is set only when adding the integration (not in Configure options)
- Non-English UI copy in all **15** locale files was reviewed and rewritten (**LLM-assisted**, automotive / Home Assistant context) to replace the initial bulk machine translation; [`scripts/generate_translations.py`](scripts/generate_translations.py) still only fills **missing** keys and does not overwrite existing strings
- Seat heat and vent select labels use **Off / Low / Medium / High** (and equivalent strings in all 15 UI locales) instead of numbered levels; automation state values remain `off`, `l1`, `l2`, `l3`
- Dropped the redundant **Engine on** binary sensor (use the **Engine** switch). Defrost and front seat heat/vent binaries remain only when the matching remote control is unavailable; with control caps they are replaced by the Defog switch / seat selects

## [0.1.3] - 2026-08-28

### Changed

- Charging tariff and petrol price number entities use **0.01** step (was whole numbers)

## [0.1.2] - 2026-08-28

### Added

- Diagnostics export includes redacted live vehicle state, resolved entity values, and registered Home Assistant entities (`entity_id`, state, attributes) per vehicle

### Changed

- Diagnostic sensors (12V, HV state, tyre temps, charge details, consumption, last updated, and related) are enabled by default on new installs; they remain under the Diagnostic entity category

### Fixed

- Cost configuration numbers (charging tariff, petrol price, petrol economy) default to **0** when unset instead of hard-coded regional sample values

## [0.1.1] - 2026-08-28

### Added

- UI translations for 15 Home Assistant locales (`en` plus `ar`, `es`, `fa`, `fr`, `he`, `id`, `kk`, `ms`, `pt`, `ru`, `th`, `vi`, `zh-Hans`, `zh-Hant`), aligned with CarLinko app languages (Simplified and Traditional Chinese as separate HA files)
- Translation key-parity tests (`tests/test_translations.py`, `tests/test_generate_translations.py`)
- Scripts to machine-fill missing locale strings from `en.json` (`scripts/generate_translations.py`, `scripts/fix_translation_placeholders.py`); default run preserves existing non-empty strings; `--force` re-translates all
- README language table and CONTRIBUTING translation workflow; `deep-translator` in `requirements-dev.txt`
- Broader debug/info/warning logging for setup, REST, WebSocket, coordinator lifecycle, entity fleet changes, and config flow; shared `partial_id()` for redacted IDs in logs; README notes on optional sub-loggers

### Fixed

- WebSocket connect uses aiohttp `ClientWSTimeout` (removes deprecation warnings under pytest)
- CI workflow uses current GitHub Actions (`checkout@v7`, `setup-python@v7`, inline pre-commit) for Node 24 runner compatibility

## [0.1.0] - 2026-08-28

### Added

- Native Home Assistant custom integration under `custom_components/carlinko/`
- Config flow (email / password / region) with reauthentication when the session or password is invalid
- WebSocket push coordinator (`cloud_push`) and spec-driven entities
- Diagnostics download (redacted)
- Protocol package shared with the optional `engine/` CLI harness

### Changed

- Product surface is the HA integration; `engine/` remains a dev-only harness
