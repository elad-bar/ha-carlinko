# TODO — close gaps vs dolphin-robot `develop`

Tracked against [sh00t2kill/dolphin-robot](https://github.com/sh00t2kill/dolphin-robot) (`develop` / `custom_components/mydolphin_plus`). CarLinko already has the factory shape (spec catalog, coordinator, reauth, diagnostics). Package layout now matches Dolphin: `common/` + `managers/` + `models/` (no `protocol/`). Engine is a single-file CLI that mounts HA-free managers/models. Behavior gaps remain.

Checkboxes are work items, not a claim that Dolphin has climate/covers. Platform-specific bugs are still listed because hassfest and users will hit them.

Suggested order: **P0 → P1 → P2 → P3** (within P0: layout first, then lifecycle / flow, then entities / translations).

---

## P0 — layout, lifecycle, config, entity identity

### Package layout (Dolphin convention)

Target shape under `custom_components/carlinko/`:

```
common/       # HA consts, base_entity, entity_descriptions, domain enums
managers/     # coordinator, store, api/ws clients, flow_manager
models/       # wire consts, exceptions, vehicle/blob DTOs, entity catalog
```

- [x] Split HA glue into `common/` + `managers/` + `models/` (former `protocol/` dissolved)
- [x] HA-free for `engine/`: `managers/` clients + `models/` must not import Home Assistant at module load; HA coordinator stays HA-only; `CarlinkoStore` is shared (HA Store or file backend)
- [x] Move root `entity.py` + `entity_setup.py` → `common/base_entity.py` + `common/entity_setup.py` (`async_setup_entities`)
- [x] Move root `coordinator.py` / `store.py` → `managers/`
- [x] Move API / WS clients → `managers/`; engine uses the same `CarlinkoStore` (file-backed)
- [ ] Extract `managers/flow_manager.py` + `models/config_data.py` from `config_flow.py` (thin flow module at package root) — deferred (flow is already small)
- [x] One consts file: `common/consts.py` (integration + wire; HA-free). Helpers in `common/helpers.py`. Platforms mapped to `Platform` in `__init__.py`.
- [x] Engine collapsed to `engine/entrypoint.py` (mounts synthetic `carlinko.managers` / `carlinko.models`)
- [x] Add empty `services.yaml` (Dolphin ships a placeholder even with no custom services)
- [ ] Optional repo companions: `info.md`, `www/` brand SVGs (HACS / Dolphin repo convention)

### Integration lifecycle (`__init__.py`)

- [ ] Typed config entry, e.g. `CarlinkoConfigEntry = ConfigEntry[CarlinkoCoordinator]`
- [ ] Store coordinator on `entry.runtime_data` instead of `hass.data[DOMAIN][entry_id]`
- [ ] `entry.async_on_unload(...)` for listeners and background tasks
- [ ] Options / data update listener that reloads the entry (Dolphin `async_reload_entry`)
- [ ] `async_migrate_entry` when `ConfigFlow.VERSION` / `MINOR_VERSION` bumps
- [ ] `async_remove_entry` that deletes store files so tokens do not linger
- [ ] Unsubscribe entity listeners when a platform unloads (`entity-event-setup`; today reload leaks listeners)

### Config flow (login is not enough)

Structure (with layout above):

- [ ] Thin `config_flow.py` + `managers/flow_manager.py` for validation / OTP-or-login / entry updates
- [ ] Schemas and defaults in `models/config_data.py`

Behavior:

- [ ] Password field via HA **password** text selector (masked)
- [ ] Region via **Select** (known codes + optional custom), not a free-form string
- [ ] **Reconfigure** flow (`SOURCE_RECONFIGURE`); README mentions it, only reauth exists
- [ ] **Options flow**: region, stream backstop, availability window, similar knobs
- [ ] **Vehicle picker** when `GET /user/vehicle` returns a list (today always `data[0]`)
- [ ] Unique id that can represent **one car per entry** (email-only unique id blocks a second vehicle on the same account)
- [ ] Abort / update existing entry when unique id already configured (Dolphin-style)

### Entity model (descriptions, not hardcoded English names)

- [ ] Add `common/entity_descriptions.py`: map HA-free catalog → HA `EntityDescription` subclasses (Dolphin `entity_descriptions`)
- [ ] Platforms import base entity / descriptions from `common/`, not package-root helpers or the HA-free catalog directly
- [ ] `EntityCategory.CONFIG` on cost numbers (`tariff`, `petrol_price`, `petrol_kml`)
- [ ] `EntityCategory.DIAGNOSTIC` on noisy / derived sensors (`updated`, HV state, tyre temps, 12V, …)
- [ ] `entity_registry_enabled_default=False` where Dolphin would hide diagnostics by default

### Translations (`key` is the identity)

Keep the HA-free catalog language-free. `key` is unique id + translation key. Do not put English (or Hebrew) strings on the catalog used by HA.

- [ ] Remove `name` from the HA-facing path (or keep English only in `engine/` for CLI logs; HA must not use it)
- [ ] HA entities: `_attr_translation_key = key`; never set `_attr_name` from catalog English
- [ ] English source in `strings.json` as `entity.{platform}.{key}.name` for every entity; keep `translations/en.json` in sync (hassfest) — today there is **no `entity` tree**
- [ ] Translate **states** for every enum sensor and select (`entity.{platform}.{key}.state.{option}`)
- [ ] Live values must be **keys** (`idle`, `normal`, `l1`), not display English (`"Normal"`, `"Check tyres"`) or HA cannot translate them
- [ ] Keep `options` / command action keys in the catalog as those machine keys (`off`, `L1`, `low`)
- [ ] Icon translations (`entity.{platform}.{key}.icon`) where there is no device class
- [ ] Config / options / reconfigure / vehicle-picker strings as those flows land; `ConfigEntryNotReady` via `translation_key`
- [ ] Add **`options`** section in `strings.json` / translations when options flow lands (Dolphin has this)
- [ ] Do not translate units (`km`, `kWh`); HA unit system handles that
- [ ] Device name stays plate/model from the car (proper nouns); no extra translation
- [ ] Optional non-English file when desired (e.g. `translations/he.json`); English-only is still translation-ready
- [ ] Engine `format_command` / logs: use catalog `key` after display `name` is gone from the HA path
- [ ] Quality scale: `entity-translations` / `icon-translations` → `done`

### Currency (use HA General, do not store IDR)

HA already has Settings → General → Currency (`hass.config.currency`). The integration still defaults to IDR / Rp / `id-ID` in the store and never asks for currency in the config flow. `tariff` / `petrol_price` have no monetary device class.

- [ ] Do not store `currency` (symbol / locale / code) in the HA store
- [ ] `tariff` and `petrol_price`: `NumberDeviceClass.MONETARY` so the unit is `hass.config.currency`
- [ ] Keep **amounts** as number entities (kWh tariff, petrol price); HA has no house electricity/petrol price
- [ ] `petrol_kml` stays a normal number (`km/L`), not monetary
- [ ] Drop IDR / `tariff_idr` defaults on the HA path
- [ ] Engine CLI may keep optional `currency` in `config.json` only
- [ ] Do **not** convert amounts when the user changes HA currency (label only, not FX)
- [ ] Future derived cost sensors: `SensorDeviceClass.MONETARY` as well

### Device registry

- [ ] Do not bake unique ids with `entry.entry_id` as `vehicle_id`; wait until real `vehicleId` is known (avoids duplicate devices after cache fill)
- [ ] Refresh `DeviceInfo` when vehicle cache updates (plate, model, VIN)
- [ ] Manufacturer / model that match the car (not always `"CarLinko"`)
- [ ] `sw_version` / `hw_version` if the API exposes them
- [ ] `serial_number` / connections from stable VIN or `deviceSn`
- [ ] Optional `configuration_url` if there is a useful cloud/app URL
- [ ] Stale-device cleanup when caps drop entities (`stale-devices`)

### Setup vs live stream (`test-before-setup`)

- [ ] Treat first successful cloud session as part of setup (login + vehicle is not enough if WS never connects)
- [ ] Keep a reconnecting WS client; do not exit the WS runner forever on a generic error
- [ ] Drive `available` / `connected` from that client the way Dolphin drives MQTT/AWS connected
- [ ] `ConfigEntryNotReady` with `translation_domain` / `translation_key` (not only `str(err)`)
- [ ] Log when entities go unavailable (`log-when-unavailable`; 40‑minute silent gap today)

### HA vs HA-free boundary (after the split)

- [ ] Remove `sys.stdout.reconfigure(...)` from the WS client
- [ ] Drop `call_soon_threadsafe` in frame handling if the WS client already runs on the HA loop
- [ ] Stop documenting env / `config.json` inside the API client as if HA used them; HA path is config entry + store
- [ ] Keep `engine/` CLI comments in `engine/`, not in HA-facing modules
- [ ] Document which packages may import `homeassistant` (`common` / `managers` / platforms) vs which must not (HA-free slice for `engine/`)

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
- [ ] `integration_type` (`device` vs `hub` — likely device per car, hub if one entry owns many)
- [ ] Align `hacs.json` with Dolphin (`iot_class`, and `filename` / `zip_release` if you ship GitHub releases)
- [ ] `info.md` at repo root (HACS detail companion; Dolphin has this)
- [ ] Optional `www/` brand assets at repo root (Dolphin convention; Core brands stay a separate PR)

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
- [ ] Config flow: cannot_connect, already_configured, reconfigure, multi-vehicle
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

- [ ] Multi-vehicle: one config entry per car, or one hub entry with multiple devices
- [ ] Reload after password/region change without deleting the integration
- [ ] `async_get_device_diagnostics` in addition to config-entry diagnostics
- [ ] `device_tracker` if the blob or REST payload has coordinates
- [ ] Speed (and other blob fields already decoded) as sensors if useful
- [ ] Repair issues for stale token / upstream outage (not only reauth popup)

---

## Already done (do not re-litigate)

Keep these; they already match the Dolphin *behavior* shape (file paths may still move in the layout pass):

- Config flow + unique id + reauth
- Coordinator owns REST + WS
- Capability-gated entity add/remove (factory helper)
- Diagnostics with redaction
- `_attr_has_entity_name`
- `iot_class: cloud_push`
- `PARALLEL_UPDATES = 1`
- Exception translations for auth / control failures
- A HA-free catalog / wire layer in `models/` (+ API/WS in `managers/`) usable from `engine/`

Not done: HA `EntityDescription` catalog, or full `entity.*` translations.

---

## Notes

- HA-free modules (`models/` + `managers/api_client.py` / `ws_client.py` / `store.py`) must not import Home Assistant at module load (`CarlinkoStore` lazy-imports HA Store only when constructed with `hass`). HA-facing code lives in `common/`, HA parts of `managers/` (coordinator), and package-root platforms. `engine/entrypoint.py` mounts a synthetic `carlinko` parent so those packages import without loading the integration `__init__`.
- Entity copy lives in `strings.json` / `translations/*.json`; description / catalog `key` is the lookup, not a display `name`.
- House currency comes from HA General (`hass.config.currency`), not a CarLinko setting.
- Custom domain services are optional; empty `services.yaml` + `action_setup: exempt` is fine if everything stays on entities.
- Core brands icons are an external PR to `home-assistant/brands`. Local `info.md` / `www/` are HACS/repo convention, not a substitute for that PR.
