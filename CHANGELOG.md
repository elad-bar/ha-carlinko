# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-08-28

### Added

- UI translations for 15 Home Assistant locales (`en` plus `ar`, `es`, `fa`, `fr`, `he`, `id`, `kk`, `ms`, `pt`, `ru`, `th`, `vi`, `zh-Hans`, `zh-Hant`), aligned with CarLinko app languages (Simplified and Traditional Chinese as separate HA files)
- Translation key-parity tests (`tests/test_translations.py`, `tests/test_generate_translations.py`)
- Scripts to machine-fill missing locale strings from `en.json` (`scripts/generate_translations.py`, `scripts/fix_translation_placeholders.py`); default run preserves existing non-empty strings; `--force` re-translates all
- README language table and CONTRIBUTING translation workflow; `deep-translator` in `requirements-dev.txt`

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
