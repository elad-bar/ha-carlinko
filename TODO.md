# TODO — close gaps vs dolphin-robot `develop`

Tracked against [sh00t2kill/dolphin-robot](https://github.com/sh00t2kill/dolphin-robot) (`develop` / `custom_components/mydolphin_plus`). CarLinko already has the factory shape (spec catalog, coordinator, reauth, diagnostics). Package layout now matches Dolphin: `common/` + `managers/` + `models/` (no `protocol/`). Engine is a single-file CLI that mounts HA-free managers/models. Behavior gaps remain.

Checkboxes are work items, not a claim that Dolphin has climate/covers. Platform-specific bugs are still listed because hassfest and users will hit them.

Suggested order: **P0 → P1 → P2 → P3** (all closed).

---

## P0 — layout, lifecycle, config, entity identity

### Package layout (Dolphin convention)

Target shape under `custom_components/carlinko/`:

```
common/       # HA consts, base_entity, entity_descriptions, domain enums
managers/     # coordinator, store, api/ws clients
models/       # wire consts, exceptions, vehicle/blob DTOs, entity catalog
```

- [x] Split HA glue into `common/` + `managers/` + `models/` (former `protocol/` dissolved)
- [x] HA-free for `engine/`: `managers/` clients + `models/` must not import Home Assistant at module load; HA coordinator stays HA-only; `CarlinkoStore` is shared (HA Store or file backend)
- [x] Move root `entity.py` + `entity_setup.py` → `common/base_entity.py` + `common/entity_setup.py` (`async_setup_entities`)
- [x] Move root `coordinator.py` / `store.py` → `managers/`
- [x] Move API / WS clients → `managers/`; engine uses the same `CarlinkoStore` (file-backed)
- [x] One consts file: `common/consts.py` (integration + wire; HA-free). Helpers in `common/helpers.py`. Platforms mapped to `Platform` in `__init__.py`.
- [x] Engine collapsed to `engine/entrypoint.py` (mounts synthetic `carlinko.managers` / `carlinko.models`)
- [x] Add empty `services.yaml` (Dolphin ships a placeholder even with no custom services)

### Integration lifecycle (`__init__.py`)

- [x] Typed config entry, e.g. `CarlinkoConfigEntry = ConfigEntry[CarlinkoCoordinator]`
- [x] Store coordinator on `entry.runtime_data` instead of `hass.data[DOMAIN][entry_id]`
- [x] `entry.async_on_unload(...)` for listeners and background tasks
- [x] Options / data update listener that reloads the entry (Dolphin `async_reload_entry`)
- [x] `async_migrate_entry` when `ConfigFlow.VERSION` / `MINOR_VERSION` bumps
- [x] `async_remove_entry` that deletes store files so tokens do not linger
- [x] Unsubscribe entity listeners when a platform unloads (`entity-event-setup`; today reload leaks listeners)

### Config flow (login is not enough)

- [x] Password field via HA **password** text selector (masked)
- [x] Region via **Select** (known codes + optional custom), not a free-form string
- [x] Region select polish: full codes (`sea`, `ap`, `emea`, `me`, `sam`, `saf`, `naf`, `uzb`, `vn`); drop `custom_value`; sort by English expansion; `selector.region` translations for display names; README marks region **required**
- [x] **Reconfigure** flow (`SOURCE_RECONFIGURE`); README mentions it, only reauth exists
- [x] **Options flow**: region, stream backstop, availability window, similar knobs
- [x] Unique id = **account email**; abort when that account is already configured (Dolphin-style)
- [x] After login, require ≥1 vehicle (`no_vehicles` abort); **no vehicle picker**
- [x] **Hub entry:** one config entry per account; **auto-add every vehicle** on that account as HA devices/entities (today API uses `data[0]` only)
- [x] On vehicle-list refresh: auto-add new cars; remove entities/devices for cars that disappeared

### Entity model (descriptions, not hardcoded English names)

- [x] Add `common/entity_descriptions.py`: map HA-free catalog → HA `EntityDescription` subclasses (Dolphin `entity_descriptions`)
- [x] Platforms import base entity / descriptions from `common/`, not package-root helpers or the HA-free catalog directly
- [x] `EntityCategory.CONFIG` on cost numbers (`tariff`, `petrol_price`, `petrol_kml`)
- [x] `EntityCategory.DIAGNOSTIC` on noisy / derived sensors (`updated`, HV state, tyre temps, 12V, …)
- [x] `entity_registry_enabled_default=False` where Dolphin would hide diagnostics by default

### Translations (`key` is the identity)

Keep the HA-free catalog language-free. `key` is unique id + translation key. Do not put English (or Hebrew) strings on the catalog used by HA.

- [x] Remove `name` from the HA-facing path (English only in `engine/` for CLI logs; HA uses translation keys)
- [x] HA entities: `_attr_translation_key = key`; never set `_attr_name` from catalog English
- [x] English source in `strings.json` as `entity.{platform}.{key}.name` for every entity; keep `translations/en.json` in sync (hassfest)
- [x] Translate **states** for every enum sensor and select (`entity.{platform}.{key}.state.{option}`)
- [x] Live values must be **keys** (`idle`, `normal`, `l1`), not display English (`"Normal"`, `"Check tyres"`) or HA cannot translate them
- [x] Keep `options` / command action keys in the catalog as those machine keys (`off`, `L1`, `low`)
- [x] Icon translations (`entity.{platform}.{key}.icon`) where there is no device class
- [x] Config / options / reconfigure / reauth strings; `ConfigEntryNotReady` via `translation_key`
- [x] **`options`** section in `strings.json` / translations (options flow already landed)
- [x] Do not translate units (`km`, `kWh`); HA unit system handles that
- [x] Device name stays plate/model from the car (proper nouns); no extra translation
- [x] English-only is translation-ready (optional `he.json` later)
- [x] Engine CLI keeps catalog `name` for logs; HA path does not use it
- [x] Quality scale: `entity-translations` / `icon-translations` ready to mark `done` in P1 yaml

### Currency (use HA General)

HA Settings → General → Currency (`hass.config.currency`). Amounts are number entities; monetary device class supplies the unit. No currency field in store / config.

- [x] Do not store `currency` (symbol / locale / code)
- [x] `tariff` and `petrol_price`: `NumberDeviceClass.MONETARY` so the unit is `hass.config.currency`
- [x] Keep **amounts** as number entities (kWh tariff, petrol price)
- [x] `petrol_kml` stays a normal number (`km/L`), not monetary
- [x] Do **not** convert amounts when the user changes HA currency (label only, not FX)

### Device registry

- [x] Do not bake unique ids with `entry.entry_id` as `vehicle_id`; wait until real `vehicleId` is known
- [x] Refresh `DeviceInfo` when vehicle cache updates (plate, model, VIN)
- [x] Manufacturer `"CarLinko"` (API has no OEM brand); model from API `model`/`modelName`
- [x] `sw_version` / `hw_version` — not exposed by API (skipped)
- [x] `serial_number` from stable VIN or `deviceSn`
- [x] `configuration_url` — no useful cloud URL (skipped)
- [x] Stale-device cleanup when vehicles leave the account (`stale-devices`)

### Setup vs live stream (`test-before-setup`)

- [x] Treat first successful cloud session as part of setup (wait for WS connected; timeout → NotReady)
- [x] Keep a reconnecting WS client; restart runner if it exits on a generic error
- [x] Drive `available` from last frame within window **and** runtime `connected`
- [x] `ConfigEntryNotReady` with `translation_domain` / `translation_key` (not only `str(err)`)
- [x] Log when entities go unavailable (`log-when-unavailable`)

### HA vs HA-free boundary (after the split)

- [x] Remove `sys.stdout.reconfigure(...)` from the WS client (engine entrypoint only)
- [x] Drop `call_soon_threadsafe` in frame handling (WS runs on the HA loop)
- [x] Stop documenting env / `config.json` inside the API client as if HA used them; HA path is config entry + store
- [x] Keep `engine/` CLI comments in `engine/`, not in HA-facing modules
- [x] Document which packages may import `homeassistant` (`common` / platforms / coordinator) vs which must not (HA-free `models/` + api/ws/store)

---

## P1 — quality scale, manifest, CI, tests

### `quality_scale.yaml`

Expand beyond the current 9 rules. Mark each `done` / `todo` / `exempt` with a one-line reason when exempt.

- [x] `brands` — local [`brand/`](custom_components/carlinko/brand/) icons (HA 2026.3+; brands CDN PR no longer accepted for custom integrations)
- [x] `reconfiguration-flow`
- [x] `entity-translations` / `icon-translations`
- [x] `entity-category`
- [x] `entity-event-setup`
- [x] `stale-devices`
- [x] `repair-issues` — exempt (reauth covers auth; no separate issue-registry repairs)
- [x] `log-when-unavailable`
- [x] `docs-*` (installation, configuration, known limitations in README)
- [x] `test-before-setup`
- [x] `config-entry-unloading` (verify after lifecycle work)
- [x] Remaining Core scale rules Dolphin tracks (appropriate-polling exempt for `cloud_push`, discovery exempt if no DHCP, etc.)

### `manifest.json` / HACS

- [x] `issue_tracker` / `documentation` / `codeowners` → [elad-bar/ha-carlinko](https://github.com/elad-bar/ha-carlinko)
- [x] `loggers`
- [x] `integration_type: hub` (one entry per account; many vehicle devices)
- [x] Align `hacs.json` with Dolphin (`iot_class: Cloud Push`; no `filename` / `zip_release` until release zips ship)

### CI (Dolphin develop is merge-gated)

- [x] GitHub Actions: **pre-commit**, **hassfest**, **HACS**, **pytest** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
- [x] Pre-commit config covering `custom_components/`, `engine/`, `tests/` ([`.pre-commit-config.yaml`](.pre-commit-config.yaml))
- [x] PR / issue templates ([`.github/`](.github/))
- [x] Make CI green (hassfest / quality-scale / entity issues from P0–P2)
- [x] `pre-commit install` locally after clone (documented in [CONTRIBUTING.md](CONTRIBUTING.md))

### Tests

- [x] `async_setup_entry` / `async_unload_entry` (including listener unsub and store cleanup)
- [x] WS connect / reconnect / auth failure after setup
- [x] Spec / description factory add/remove when caps or PHEV/TPMS flags change
- [x] One test per platform entity class (lock, climate, cover, switch, select, number, button, sensors)
- [x] Config flow: cannot_connect, already_configured (account), reconfigure, multi-vehicle auto-add (no picker)
- [x] After layout: `engine/` still imports the HA-free slice; platforms go through `common` setup helper
- [x] Sensor/cover/seat/climate semantics (energy_storage, TPMS unit, distance, timestamp, no SET_POSITION)
- Note: full HA pytest plugin suite is skipped on Windows (`fcntl`); CI Linux runs everything.

---

## P2 — entity correctness (hassfest / HA semantics)

- [x] **Cover:** do not set `SET_POSITION` unless `async_set_cover_position` exists. Vent/tilt → extra buttons or tilt position, not fake position
- [x] **Climate:** use caps `ac.min` / `ac.max` / `ac.step` and blob `ac_temp`; target temperature; heat/auto if opcodes exist
- [x] **`energy_left`:** `device_class=energy` + `state_class=measurement` is invalid; use a storage-appropriate class or drop energy class
- [x] **TPMS:** `device_class=pressure` requires a native unit (PSI or kPa)
- [x] **Range / odometer:** `UnitOfLength.KILOMETERS` and `SensorDeviceClass.DISTANCE` where applicable (not raw `"km"`)
- [x] **`updated`:** timestamp device class needs a timezone-aware `datetime`, not a raw string path
- [x] **Seat selects:** no live `current_option` until levels exist — hide, unknown, or binary until state is real
- [x] Prefer HA unit / device-class constants in `common/entity_descriptions.py` (Dolphin style); the HA-free catalog may stay stringly typed

---

## P3 — product extras Dolphin solved in config / diagnostics

- [x] Multi-vehicle hub runtime: per-vehicle devices/entities, caps/WS keyed by `vehicle_id`, store holds vehicles map (see P0 config flow)
- [x] Reload after password/region change without deleting the integration
- [x] `async_get_device_diagnostics` in addition to config-entry diagnostics
- [x] Speed sensor from decoded blob `speed_calculated` (`km/h`)

Not pursued: `device_tracker` (no lat/lon in blob/REST); repair issues (quality scale exempt — reauth + unavailable cover auth/outage).

---

## Already done (do not re-litigate)

Keep these; they already match the Dolphin _behavior_ shape:

- Config flow + unique id + reauth (+ reconfigure / options; schemas stay in `config_flow.py`)
- Coordinator owns REST + WS (setup waits for first WS session)
- Capability-gated entity add/remove (factory helper)
- Diagnostics with redaction (config entry + per-device)
- `_attr_has_entity_name` + `_attr_translation_key` + `common/entity_descriptions.py`
- Full `entity.*` trees in `strings.json` / `translations/en.json`
- `iot_class: cloud_push`
- `PARALLEL_UPDATES = 1`
- Exception translations for auth / control failures
- A HA-free catalog / wire layer in `models/` (+ API/WS in `managers/`) usable from `engine/`
- HACS detail via `hacs.json` `render_readme: true` (no separate `info.md`; repo-root `www/` is brand source only)
- HA currency from Settings → General; monetary number device class on tariff / petrol_price
- Speed sensor from live blob

---

## Notes

- HA-free modules (`models/` + `managers/api_client.py` / `ws_client.py` / `store.py`) must not import Home Assistant at all (`CarlinkoStore` takes a pre-built HA `Store` from HA-facing callers). HA-facing code lives in `common/`, HA parts of `managers/` (coordinator), and package-root platforms. `engine/entrypoint.py` mounts a synthetic `carlinko` parent so those packages import without loading the integration `__init__`.
- Entity copy lives in `strings.json` / `translations/*.json`; description / catalog `key` is the lookup, not a display `name`.
- House currency comes from HA General (`hass.config.currency`); CarLinko never stores a currency code.
- Custom domain services are optional; empty `services.yaml` + `action_setup: exempt` is fine if everything stays on entities.
- Brand icons live in `custom_components/carlinko/brand/` (HA 2026.3+ local brand images); `www/` is the repo README source copy.
