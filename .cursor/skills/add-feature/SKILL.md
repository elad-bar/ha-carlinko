---
name: add-feature
description: >-
  Implements a new CarLinko integration feature in the correct layer (entity
  catalog, REST/WS, service, options, or engine-only) with translations, tests,
  and PR metadata. Use when adding a feature, new entity, new service, options
  field, API/WebSocket capability, or engine-only change.
---

# Add a feature

Read before editing:

- [docs/standards/coding.md](../../../docs/standards/coding.md)
- [docs/standards/testing.md](../../../docs/standards/testing.md)
- [docs/standards/ci.md](../../../docs/standards/ci.md)

## Checklist

1. **Classify**: entity / REST or WS / HA service / options / engine-only.
2. **Place the code** in the matching layer. Platforms stay thin. Do not add engine Python besides `engine/entrypoint.py`. Do not import `homeassistant` in HA-free modules; extend `tests/test_ha_free_imports.py` if you add one.
3. **Entities / strings:** `EntitySpec` first, then descriptions/platform only if needed. Update `strings.json` and `translations/en.json` together. If English terms were added or changed, follow [translate-locales](../translate-locales/SKILL.md). Translation procedure: [CONTRIBUTING.md](../../../CONTRIBUTING.md).
4. **Controls / API**: opcodes in `EntitySpec.commands`; catalog in [docs/control-opcodes.md](../../../docs/control-opcodes.md). REST/WS: [docs/api-map.md](../../../docs/api-map.md), [docs/api-contracts.md](../../../docs/api-contracts.md). No `startUpgradeFirmware`.
5. **Logs**: follow [docs/logging.md](../../../docs/logging.md). No secrets, VIN, or plate.
6. **Tests**: add or extend per testing.md. New behavior is not docs-only.
7. **Version and changelog**: follow [changelog-version](../changelog-version/SKILL.md) (`### Added` or `### Changed`).
8. **Before PR:** from repo root, `pre-commit run --all-files`. If it fails, fix the reported issues (including files the hooks auto-format) and run again until it is clean. Do not skip hooks. Then `pytest` (full suite in Linux if HA plugin tests changed — [testing.md](../../../docs/standards/testing.md)).
9. **PR**: one feature. Fill car/region and confirmed vs inferred. Keep CI jobs as they are.
