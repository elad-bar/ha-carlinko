# Coding standards

How we write Python in this repo. Product rules (entities, opcodes, translations, confirmed vs inferred) live in [CONTRIBUTING.md](../../CONTRIBUTING.md) and the Cursor skills under `.cursor/skills/`. Tests and CI: [testing.md](testing.md), [ci.md](ci.md).

Formatting is [pre-commit](../../.pre-commit-config.yaml) (Black, isort, flake8, pyupgrade `--py39-plus`, bandit on `custom_components/`, prettier). Run `pre-commit run --all-files`. Do not hand-format against a different style.

CI runs Python **3.13**. Black/pyupgrade still target **3.9+**. Runtime deps: [`requirements.txt`](../../requirements.txt). Test/hook deps: [`requirements-dev.txt`](../../requirements-dev.txt).

## Directory structure

Two roots. Do not flatten `common/`, `managers/`, `models/`, or `translations/` onto the **project** root.

**Project root** (repo):

| Folder                        | Put here                                                         | Do not put here                         |
| ----------------------------- | ---------------------------------------------------------------- | --------------------------------------- |
| `custom_components/carlinko/` | The Home Assistant integration package (see below)               | —                                       |
| `engine/`                     | CLI harness only ([`entrypoint.py`](../../engine/entrypoint.py)) | A second copy of clients or models      |
| `tests/`                      | pytest                                                           | Runtime code                            |
| `docs/`                       | Standards and domain docs                                        | Code                                    |
| `scripts/`                    | One-off generators                                               | Imports from the integration at runtime |

**Package root** (`custom_components/carlinko/`):

| Folder / files     | Put here                                                                                                                                               | Do not put here                          |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| Package root files | HA entry: `__init__.py`, `config_flow.py`, `diagnostics.py`, `manifest.json`, `services.py` / `services.yaml`, `strings.json`, one module per platform | Decode, HTTP, blob parsing               |
| `common/`          | Constants, pure helpers, HA entity base/setup shared by platforms                                                                                      | Vendor HTTP, per-platform entity classes |
| `managers/`        | Long-lived I/O and orchestration: HTTP, WebSocket, persistence, HA coordinator                                                                         | Data catalogs, payload decode            |
| `models/`          | Data shapes, decode, catalogs, protocol exceptions — no I/O                                                                                            | `aiohttp`, config entries, platforms     |
| `translations/`    | HA locale JSON (`en.json`, …)                                                                                                                          | Python                                   |

**Fit:** network I/O → package `managers/`; typed facts about payloads/state → package `models/`; shared and not I/O → package `common/`; HA platform registration → thin `*.py` next to those folders. Native Home Assistant is the product; the engine only mounts the same package. See [engine/README.md](../../engine/README.md).

**HA-free:** `models/`, `managers/api_client.py`, `ws_client.py`, `store.py`, and `common/consts.py` must not import `homeassistant`. Coordinator, platforms, config flow, and HA-facing `common/` may. Enforced by [`tests/test_ha_free_imports.py`](../../tests/test_ha_free_imports.py) — extend `_HA_FREE_MODULES` when you add another HA-free module.

## File shape

**Class is the default** for domain and I/O files: one primary class per module. Small functions in the same file are fine when they do not need `self` (e.g. `vehicle_id_of` next to `ApiClient`, `async_setup_entry` next to the entity class).

Do not invent a helpers class of only `@staticmethod`s.

| Kind                                                                       | Shape                                                         |
| -------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Managers, models, config/options flows, platforms, `common/base_entity.py` | **Class file**                                                |
| `common/consts.py`, `common/helpers.py`                                    | **Functions / constants / enums only**                        |
| HA glue: `__init__.py`, `diagnostics.py`, `services.py`                    | **Function files** — that is Home Assistant’s API             |
| Common factories: `entity_setup.py`, `entity_descriptions.py`              | **Function files** — spec → entities / `EntityDescription`    |
| Engine `entrypoint.py`                                                     | Functions and `async def main` — no extra engine Python files |

**Platforms:** `async_setup_entry` plus **one** entity class; no second entity type in that file.

**`common/` is mixed:** `base_entity.py` is a class; consts/helpers and the two factories are functions. Do not turn `__init__.py`, diagnostics, or services into classes.

## Imports

1. Module docstring.
2. `from __future__ import annotations`
3. **Stdlib**, then **third party**, then **first party** (isort, Black profile). `homeassistant` and `tests` are first-party in [`pyproject.toml`](../../pyproject.toml).
4. Inside the integration package, use **relative** imports (`.common`, `..models`). Engine uses **absolute** `carlinko.*` after the HA-free path mount.
5. Then `_LOGGER` / module constants, then code.

**Always import at the top of the file.** Never import inside a function, method, or class body.

**Never use conditional imports:** no `if …: import`, no `try/except ImportError` around imports, no `if TYPE_CHECKING:` import blocks. If a cycle appears, split modules rather than hiding the import.

**Exception:** [`tests/conftest.py`](../../tests/conftest.py) may `try: import fcntl` so Windows can skip the HA pytest plugin. No other file gets this exception.

## Strings

- Use **f-strings** for values, paths, exceptions, and log messages (`f"invalid region={region!r}"`). Do not use `'{}'.format()` or `%` interpolation for ordinary Python strings.
- Prefer `key=value` fragments over prose. Use `!r` for raw or invalid input.
- User-visible UI copy belongs in `strings.json` / translations, not concatenated English in Python.

New engine log lines should use f-strings as well (some older CLI lines still use `%s`).

## Logging

Shared contract for integration and engine. Named HA lines, flows, and `caplog` examples: [logging.md](../logging.md).

**Who logs.** `_LOGGER = logging.getLogger(__name__)`. No `print` in library code. Do not invent extra logger names. `models/` do not log (decode is silent). Thin platforms (`sensor.py`, `lock.py`, …) do not log; add a logger only if the module owns a user-visible action (remote control, local config). `services.py` may DEBUG register/unregister.

**Who configures.** Only Home Assistant (integration) and `engine/entrypoint.py` (harness) attach handlers or set the root level. Managers and models never call `basicConfig`, never add handlers. The integration registers the parent logger in `manifest.json` (`custom_components.carlinko`); child `__name__` loggers inherit — do not add extra `loggers` entries.

**Levels.** DEBUG = path/attempt; INFO = outcome/milestone; WARNING = expected failure; ERROR / `exception` = cannot continue / unexpected. Do not log the same fact at INFO and DEBUG. The layer that owns the result logs it; callers do not repeat it.

**Exceptions.** Unexpected failure in `except`: `_LOGGER.exception("…")` (traceback). Do not also paste `error={err}` into that message. Recoverable fallback (try timestamp, then continue): `_LOGGER.debug("…", exc_info=True)` so INFO stays clean. Transient stream drop: `_LOGGER.warning("…", exc_info=True)` then reconnect.

**Message shape.** Stable grep-friendly prefixes (`login ok`, `auth failure source=`). `key=value` fragments. Tests assert those substrings, so do not churn them. Truncate large DEBUG lists (entity key lists: names only if few, else count). HTTP/WS DEBUG is method + path or connect attempt `i/n` — not bodies, tokens, or frame payloads.

**Redaction.** Never log passwords, tokens, sign keys, full request/response bodies, VIN, or plate. Use `partial_id` / `mask_email`. (Availability INFO currently logs a full vehicle id by existing convention — see logging.md; do not spread that pattern.)

**Diagnostics vs logs.** In-memory HTTP snapshots for HA diagnostics (`ApiClient` query log) are not `_LOGGER`. Do not INFO-dump those records. Login / remoteControl stay out of that snapshot store.

**Home Assistant:** do not attach handlers. HA sets the level for `custom_components.carlinko`.

**Engine:** may configure logging in `entrypoint.py` (stdout, `CARLINKO_LOG_LEVEL` / `DEBUG=true`, quieter `aiohttp` loggers). Default INFO. Same client loggers, not a parallel `print` protocol. Entity deltas on stdout are the harness; new engine code uses `_LOGGER` and f-strings (do not log raw API payloads on failure).

## HTTP and WebSocket

**One stack: `aiohttp`.** HTTP via `ClientSession` and `ClientTimeout`; WebSocket via that same session. Do not add `requests`, `httpx`, or another WS library.

- Timeouts are explicit.
- Own the session at the coordinator or engine boundary; pass it into clients. Do not open a process-wide session per new endpoint — add a method on the existing API client.
- `python-dotenv` is engine-only. Integration credentials come from the config entry.

## Safety

Never commit, screenshot, or paste `.env`, `config.json`, tokens, API keys, VIN, or plate.
