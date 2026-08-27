# TODO — close gaps vs dolphin-robot `develop`

Tracked against [sh00t2kill/dolphin-robot](https://github.com/sh00t2kill/dolphin-robot) (`develop` / `custom_components/mydolphin_plus`). CarLinko already has the factory shape (spec catalog, coordinator, reauth, diagnostics). Package layout now matches Dolphin: `common/` + `managers/` + `models/` (no `protocol/`). Engine is a single-file CLI that mounts HA-free managers/models. Behavior gaps remain.

Checkboxes are work items, not a claim that Dolphin has climate/covers. Platform-specific bugs are still listed because hassfest and users will hit them.

Suggested order: **P0 → P1 → P2 → P3** (P0 closed; next is P1 quality scale / CI / tests).

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
- [ ] Future derived cost sensors: `SensorDeviceClass.MONETARY` as well (P3 when added)

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

- [ ] `brands` — custom icons in [home-assistant/brands](https://github.com/home-assistant/brands)
- [ ] `reconfiguration-flow`
- [ ] `entity-translations` / `icon-translations`
- [ ] `entity-category`
- [ ] `entity-event-setup`
- [ ] `stale-devices`
- [ ] `repair-issues` — HA issue registry in addition to `async_start_reauth`
- [ ] `log-when-unavailable`
- [ ] `docs-*` (installation, configuration, known limitations)
- [ ] `test-before-setup`
- [ ] `config-entry-unloading` (verify after lifecycle work)
- [ ] Remaining Core scale rules Dolphin tracks (appropriate-polling exempt for `cloud_push`, discovery exempt if no DHCP, etc.)

### `manifest.json` / HACS

- [x] `issue_tracker` / `documentation` / `codeowners` → [elad-bar/ha-carlinko](https://github.com/elad-bar/ha-carlinko)
- [ ] `loggers`
- [x] `integration_type: hub` (one entry per account; many vehicle devices)
- [ ] Align `hacs.json` with Dolphin (`iot_class`, and `filename` / `zip_release` if you ship GitHub releases)

### CI (Dolphin develop is merge-gated)

- [x] GitHub Actions: **pre-commit**, **hassfest**, **HACS**, **pytest** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
- [x] Pre-commit config covering `custom_components/`, `engine/`, `tests/` ([`.pre-commit-config.yaml`](.pre-commit-config.yaml))
- [x] PR / issue templates ([`.github/`](.github/))
- [ ] Make CI green (hassfest / quality-scale / entity issues from P0–P2 will fail until those land)
- [ ] `pre-commit install` locally after clone (`pip install -r requirements-dev.txt && pre-commit install`)

### Tests

- [ ] `async_setup_entry` / `async_unload_entry` (including listener unsub and store cleanup)
- [ ] WS connect / reconnect / auth failure after setup
- [ ] Spec / description factory add/remove when caps or PHEV/TPMS flags change
- [ ] One test per platform entity class (lock, climate, cover, switch, select, number, button, sensors)
- [x] Config flow: cannot_connect, already_configured (account), reconfigure, multi-vehicle auto-add (no picker)
- [ ] Diagnostics: device-level if added
- [ ] After layout: `engine/` still imports the HA-free slice; platforms go through `common` setup helper

---

## P2 — entity correctness (hassfest / HA semantics)

- [ ] **Cover:** do not set `SET_POSITION` unless `async_set_cover_position` exists. Vent/tilt → extra buttons or tilt position, not fake position
- [ ] **Climate:** use caps `ac.min` / `ac.max` / `ac.step` and blob `ac_temp`; target temperature; heat/auto if opcodes exist
- [ ] **`energy_left`:** `device_class=energy` + `state_class=measurement` is invalid; use a storage-appropriate class or drop energy class
- [ ] **TPMS:** `device_class=pressure` requires a native unit (PSI or kPa)
- [ ] **Range / odometer:** `UnitOfLength.KILOMETERS` and `SensorDeviceClass.DISTANCE` where applicable (not raw `"km"`)
- [ ] **`updated`:** timestamp device class needs a timezone-aware `datetime`, not a raw string path
- [ ] **Seat selects:** no live `current_option` until levels exist — hide, unknown, or binary until state is real
- [ ] Prefer HA unit / device-class constants in `common/entity_descriptions.py` (Dolphin style); the HA-free catalog may stay stringly typed

---

## P3 — product extras Dolphin solved in config / diagnostics

- [x] Multi-vehicle hub runtime: per-vehicle devices/entities, caps/WS keyed by `vehicle_id`, store holds vehicles map (see P0 config flow)
- [x] Reload after password/region change without deleting the integration
- [ ] `async_get_device_diagnostics` in addition to config-entry diagnostics
- [ ] `device_tracker` if the blob or REST payload has coordinates
- [ ] Speed (and other blob fields already decoded) as sensors if useful
- [ ] Repair issues for stale token / upstream outage (not only reauth popup)

---

## Already done (do not re-litigate)

Keep these; they already match the Dolphin *behavior* shape:

- Config flow + unique id + reauth (+ reconfigure / options; schemas stay in `config_flow.py`)
- Coordinator owns REST + WS (setup waits for first WS session)
- Capability-gated entity add/remove (factory helper)
- Diagnostics with redaction
- `_attr_has_entity_name` + `_attr_translation_key` + `common/entity_descriptions.py`
- Full `entity.*` trees in `strings.json` / `translations/en.json`
- `iot_class: cloud_push`
- `PARALLEL_UPDATES = 1`
- Exception translations for auth / control failures
- A HA-free catalog / wire layer in `models/` (+ API/WS in `managers/`) usable from `engine/`
- HACS detail via `hacs.json` `render_readme: true` (no separate `info.md` / `www/`)
- HA currency from Settings → General; monetary number device class on tariff / petrol_price

Not done (P1+): quality_scale expansion, remaining CI green, platform hassfest fixes (P2), device diagnostics / repair issues (P3).

---

## Notes

- HA-free modules (`models/` + `managers/api_client.py` / `ws_client.py` / `store.py`) must not import Home Assistant at all (`CarlinkoStore` takes a pre-built HA ``Store`` from HA-facing callers). HA-facing code lives in `common/`, HA parts of `managers/` (coordinator), and package-root platforms. `engine/entrypoint.py` mounts a synthetic `carlinko` parent so those packages import without loading the integration `__init__`.
- Entity copy lives in `strings.json` / `translations/*.json`; description / catalog `key` is the lookup, not a display `name`.
- House currency comes from HA General (`hass.config.currency`); CarLinko never stores a currency code.
- Custom domain services are optional; empty `services.yaml` + `action_setup: exempt` is fine if everything stays on entities.
- Core brands icons are an external PR to `home-assistant/brands` (not local repo assets).
