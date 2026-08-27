# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-08-28

### Added

- Native Home Assistant custom integration under `custom_components/carlinko/`
- Config flow (email / password / region) with reauthentication when the session or password is invalid
- WebSocket push coordinator (`cloud_push`) and spec-driven entities
- Diagnostics download (redacted)
- Protocol package shared with the optional `engine/` CLI harness

### Changed

- Product surface is the HA integration; `engine/` remains a dev-only harness
