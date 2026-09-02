# Testing standards

Run `pytest` from the **repo root**. There is no coverage gate.

[CI](ci.md) (Ubuntu, Python 3.13) is the authority for the **full** suite, including Home Assistant plugin tests.

## Windows vs Linux

[`tests/conftest.py`](../../tests/conftest.py) loads `pytest_homeassistant_custom_component` only when `fcntl` exists. Native Windows Python does not; those modules are skipped:

- `test_config_flow.py`
- `test_coordinator.py`
- `test_setup_unload.py`

All other tests still run on a Windows host. A green native Windows `pytest` is **not** the same as CI if you changed config flow, coordinator, or setup/unload.

**Full suite on a Windows machine:** run pytest in **Linux** — WSL2 or a Linux Docker container (Docker Engine). Inside that environment `fcntl` works and nothing is skipped. There is no checked-in image yet; any Python 3.13 Linux environment with `requirements.txt` + `requirements-dev.txt` is enough. Do not detect Docker from Windows `conftest` — if pytest is already in Linux, the skip does not apply.

## What to test where

Prefer HA-free unit tests for decode, REST/WS clients, and store. Use the HA plugin (`hass`, `MockConfigEntry`) for config flow, coordinator, and setup/unload.

| Change                                      | Extend or add                                                                                                 |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Catalog / descriptions / platform semantics | `test_entity_semantics.py`, `test_platform_entities.py`, `test_entity_setup.py`                               |
| New HA-free module                          | `_HA_FREE_MODULES` in `test_ha_free_imports.py`                                                               |
| UI strings / locales                        | `test_translations.py` (and `test_generate_translations.py` if the generator changes)                         |
| REST / logging around API                   | `test_api_rest.py`, `test_api_client_logging.py`                                                              |
| Location, store, diagnostics                | `test_location.py`, `test_store.py`, `test_diagnostics.py`                                                    |
| Config flow, coordinator, load/unload       | `test_config_flow.py`, `test_coordinator.py`, `test_setup_unload.py` (full suite: CI / WSL / Linux container) |
| Manifest version bump                       | `test_changelog_release.py` — changelog must have a matching `## [x.y.z]` section                             |

## When a test is required

- New behavior: add or extend a test unless the change is docs-only.
- Bug fix: add or extend a test that would have failed before the fix, when that is practical.
- Do not skip tests to land a change. Do not add a job-wide coverage number.

Pytest config lives in [`pyproject.toml`](../../pyproject.toml) (`[tool.pytest.ini_options]`).
