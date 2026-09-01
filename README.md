# CarLinko

<p align="center">
  <img src="www/logo.png" alt="CarLinko" width="320" />
</p>

Home Assistant custom integration for Chery Group / CarLinko connected cars
(BEV and PHEV). Live state over the CarLinko WebSocket (`cloud_push`), with
remote controls through the official cloud API.

Not affiliated with Jaecoo, Chery, or CarLinko.

Based on
[GodrezJr2/j5-ev-dashboard](https://github.com/GodrezJr2/j5-ev-dashboard),
used as the starting point for this custom component.

Home Assistant UI brand icons ship in
[`custom_components/carlinko/brand/`](custom_components/carlinko/brand/)
(HA 2026.3+ local brand images; mirrored from [`www/`](www/)).

## Prerequisites

- Home Assistant (see `hacs.json` for the tested version)
- A CarLinko app account with **at least one** paired vehicle you own
- Network access from Home Assistant to CarLinko cloud services

## Install

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories
   Add this repo as type **Integration** (until it is listed in HACS).
2. Install **CarLinko**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **CarLinko**.
4. Enter email, password, and region (e.g. Southeast Asia / `sea`).

### Manual

Copy `custom_components/carlinko/` into
`<config>/custom_components/carlinko/`, restart, then add the integration.

## Configuration

### Setup

| Field    | Required | Description                                        |
| -------- | -------- | -------------------------------------------------- |
| Email    | yes      | CarLinko account email                             |
| Password | yes      | CarLinko account password                          |
| Region   | yes      | Cloud region matching the CarLinko app (see below) |

Must match the region used in the CarLinko app. Stored value is the code;
the UI shows the full name.

| Code   | Region                       |
| ------ | ---------------------------- |
| `ap`   | Asia Pacific                 |
| `emea` | Europe, Middle East & Africa |
| `me`   | Middle East                  |
| `naf`  | North Africa                 |
| `saf`  | South Africa                 |
| `sam`  | South America                |
| `sea`  | Southeast Asia               |
| `uzb`  | Uzbekistan                   |
| `vn`   | Vietnam                      |

On submit, the integration logs in against CarLinko and stores the session.
One config entry is created **per account** (hub): every vehicle on that account
is added automatically as HA devices/entities — there is no vehicle picker.

If the token goes stale, Home Assistant prompts for **re-authentication**
(password only; email and region are unchanged). To use a different cloud region,
remove the integration and add it again with the correct region.

| Error                     | Meaning                    |
| ------------------------- | -------------------------- |
| Invalid email or password | Auth rejected              |
| Could not reach CarLinko  | Network / upstream failure |
| Unexpected error          | See logs                   |
| Already configured        | Same account already added |
| No vehicles               | Account has no paired cars |

### Options

After setup, configure via the integration’s **Configure** options flow:

| Option                        | Default          | Description                                            |
| ----------------------------- | ---------------- | ------------------------------------------------------ |
| Stream backstop (seconds)     | `20`             | WS keepalive / re-request interval                     |
| Availability window (seconds) | `2400` (~40 min) | Entities go unavailable if no frame within this window |

## Behaviour

- Push updates over the CarLinko WebSocket (`iot_class: cloud_push`).
- Vehicle **location** uses a separate REST call (`/maps/deviceLocate`), probed at
  setup and polled every 15 minutes when the car supports it.
- **Notices** (operational types vehicle/control only): polled every 5 minutes;
  new rows fire a `carlinko_notice` event. Marketing/CMS announcements are ignored.
  List on demand via service `carlinko.get_notices`.
- **Service history**: summary sensors refreshed every 12 hours; full list/details
  via `carlinko.get_maintain_history` / `carlinko.get_maintain_details`.
- **Firmware**: read-only check at startup and every 24 hours (plus
  `carlinko.check_firmware`). Does not download or start OTA. Until a real
  current firmware string is known, the probe may use `0.0.0` as the baseline.
- Entities come from the HA-free catalog in
  [`models/entity_specs.py`](custom_components/carlinko/models/entity_specs.py).
- PHEV, direct TPMS, and capability-gated controls appear when the car reports
  them; entities are added/removed as that set changes.
- Cost knobs (`tariff`, `petrol_price`, `petrol_kml`) persist in HA storage.
- Currency for monetary amounts comes from Home Assistant **Settings → General**;
  CarLinko does not store a currency code or convert amounts on currency change.

### Languages

Entity names, config flow text, and enum state labels follow **Settings → System →
General → Language**. Shipped UI translations live under
[`custom_components/carlinko/translations/`](custom_components/carlinko/translations/).
If your HA language has no matching file below, strings fall back to English.

| HA locale | Language              |
| --------- | --------------------- |
| `en`      | English               |
| `ar`      | Arabic                |
| `es`      | Spanish               |
| `fa`      | Persian (Farsi)       |
| `fr`      | French                |
| `he`      | Hebrew                |
| `id`      | Indonesian            |
| `kk`      | Kazakh                |
| `ms`      | Malay                 |
| `pt`      | Portuguese            |
| `ru`      | Russian               |
| `th`      | Thai                  |
| `vi`      | Vietnamese            |
| `zh-Hans` | Chinese (Simplified)  |
| `zh-Hant` | Chinese (Traditional) |

These locales align with the CarLinko mobile app language set, with Simplified and
Traditional Chinese as separate HA files (`zh-Hans` / `zh-Hant`) instead of the app’s
single `zh` code.

Non-English locales were first bootstrapped with machine translation
([`scripts/generate_translations.py`](scripts/generate_translations.py), Google
Translate). Shipped strings are being **revised with LLM-assisted review** (car
terminology, select states, config-flow wording) across all files under
[`translations/`](custom_components/carlinko/translations/). That pass does not
replace native review — corrections from fluent speakers are still welcome; see
[Contributing](CONTRIBUTING.md#translations). Re-running the generator only fills
**missing** keys; it does not replace strings that were already improved by hand
or in a locale review.

## Entities

Default English names (translated in the UI). Entities are grouped by the filter
that decides whether they are created for your car. If a group does not apply, none
of its rows appear on the device.

### All vehicles

Standard telemetry and cost settings for every paired BEV or PHEV — no extra
powertrain, TPMS, or remote-control check.

| Name             | Entity type   | Unit of measurement | Comments                                                         |
| ---------------- | ------------- | ------------------- | ---------------------------------------------------------------- |
| Battery          | Sensor        | %                   | —                                                                |
| Range            | Sensor        | km                  | —                                                                |
| Odometer         | Sensor        | km                  | —                                                                |
| Speed            | Sensor        | km/h                | —                                                                |
| 12V Battery      | Sensor        | V                   | Diagnostic category                                              |
| 12V status       | Sensor        | —                   | Diagnostic category; available options: OK, Low, Critical        |
| Charge Power     | Sensor        | kW                  | Diagnostic category                                              |
| Consumption      | Sensor        | kWh/100km           | Diagnostic category                                              |
| Charge remaining | Sensor        | min                 | Diagnostic category                                              |
| Charge mode      | Sensor        | —                   | Diagnostic category; available options: None, AC, DC             |
| Charge state     | Sensor        | —                   | Available options: Idle, Charging, Complete, Canceled, Hot, Stop |
| HV state         | Sensor        | —                   | Diagnostic category; available options: Off, LV, Ready, Unknown  |
| Rated range      | Sensor        | km                  | —                                                                |
| Energy left      | Sensor        | kWh                 | —                                                                |
| Tyre status      | Sensor        | —                   | Available options: Normal, Check tyres                           |
| Charging         | Binary sensor | —                   | —                                                                |
| Online           | Binary sensor | —                   | —                                                                |
| Moving           | Binary sensor | —                   | —                                                                |
| Tyre problem     | Binary sensor | —                   | —                                                                |
| Any door         | Binary sensor | —                   | —                                                                |
| Driver door      | Binary sensor | —                   | —                                                                |
| Passenger door   | Binary sensor | —                   | —                                                                |
| Rear left door   | Binary sensor | —                   | —                                                                |
| Rear right door  | Binary sensor | —                   | —                                                                |
| Seat heat left   | Binary sensor | —                   | Status only when seat heat remote control is unavailable         |
| Seat heat right  | Binary sensor | —                   | Status only when seat heat remote control is unavailable         |
| Seat vent left   | Binary sensor | —                   | Status only when seat vent remote control is unavailable         |
| Seat vent right  | Binary sensor | —                   | Status only when seat vent remote control is unavailable         |
| Defrost          | Binary sensor | —                   | Status only when defog remote control is unavailable             |
| Charging tariff  | Number        | currency            | Config category; numeric 0–10,000,000 (step 0.01); HA currency   |
| Petrol price     | Number        | currency            | Config category; numeric 0–10,000,000 (step 0.01); HA currency   |
| Petrol economy   | Number        | km/L                | Config category; numeric 0–100 (step 0.1)                        |

### PHEV

Plug-in hybrid only (`powertrain == phev`): fuel tank and blended range from the
status stream.

| Name             | Entity type | Unit of measurement | Comments |
| ---------------- | ----------- | ------------------- | -------- |
| Fuel             | Sensor      | %                   | —        |
| Fuel range       | Sensor      | km                  | —        |
| Total range      | Sensor      | km                  | —        |
| Fuel consumption | Sensor      | L/100km             | —        |

### Direct TPMS

Per-wheel tyre pressure and temperature in the status blob (`tyre_indirect` is
false). Indirect “check tyres” warnings alone do not enable this group.

| Name             | Entity type | Unit of measurement | Comments            |
| ---------------- | ----------- | ------------------- | ------------------- |
| Front left       | Sensor      | psi                 | —                   |
| Front left temp  | Sensor      | °C                  | Diagnostic category |
| Front right      | Sensor      | psi                 | —                   |
| Front right temp | Sensor      | °C                  | Diagnostic category |
| Rear left        | Sensor      | psi                 | —                   |
| Rear left temp   | Sensor      | °C                  | Diagnostic category |
| Rear right       | Sensor      | psi                 | —                   |
| Rear right temp  | Sensor      | °C                  | Diagnostic category |

### Remote control

CarLinko exposes the function in `vehicleControlConfig` for your VIN (`cap:…` in
the catalog).

| Name                | Entity type    | Unit of measurement | Comments                                    |
| ------------------- | -------------- | ------------------- | ------------------------------------------- |
| Lock                | Lock           | —                   | —                                           |
| Climate             | Climate        | —                   | —                                           |
| Windows             | Cover          | —                   | —                                           |
| Sunroof             | Cover          | —                   | —                                           |
| Liftgate            | Cover          | —                   | —                                           |
| Windows vent        | Button         | —                   | —                                           |
| Sunroof tilt        | Button         | —                   | —                                           |
| Find car            | Button         | —                   | —                                           |
| Location            | Device tracker | —                   | Maps locate; created when cloud supports it |
| Stop charging       | Button         | —                   | —                                           |
| Engine              | Switch         | —                   | —                                           |
| Gear                | Select         | —                   | Available options: Low, High                |
| Quick cool          | Button         | —                   | —                                           |
| Quick heat          | Button         | —                   | —                                           |
| Defog               | Switch         | —                   | —                                           |
| Air purify          | Switch         | —                   | —                                           |
| Driver seat heat    | Select         | —                   | Available options: Off, Low, Medium, High   |
| Driver seat vent    | Select         | —                   | Available options: Off, Low, Medium, High   |
| Passenger seat heat | Select         | —                   | Available options: Off, Low, Medium, High   |
| Passenger seat vent | Select         | —                   | Available options: Off, Low, Medium, High   |
| Rear L seat heat    | Select         | —                   | Available options: Off, Low, Medium, High   |
| Rear L seat vent    | Select         | —                   | Available options: Off, Low, Medium, High   |
| Rear R seat heat    | Select         | —                   | Available options: Off, Low, Medium, High   |
| Rear R seat vent    | Select         | —                   | Available options: Off, Low, Medium, High   |

Catalog source and opcodes: [`entity_specs.py`](custom_components/carlinko/models/entity_specs.py),
[`docs/control-opcodes.md`](docs/control-opcodes.md).

File a [compatibility report](https://github.com/elad-bar/ha-carlinko/issues/new?template=compatibility.md)
if you try another model.

## Known limitations

- Undocumented vendor API — no warranty; backends can change without notice.
- Entities are capability-gated: only features the car reports are created.
- Remote actions are real cloud actuation — use only on a car you own.
- API does not expose OEM brand, `sw_version` / `hw_version`, or a useful
  `configuration_url`.
- Entities go unavailable after the availability window without a fresh frame
  (default ~40 minutes). Device tracker also requires a successful locate fix.
- Location may stay unavailable (`50052`) while the car is offline or has no GPS
  fix; unsupported cars (`50049`) never get a tracker entity.

## Legal & ethics

- Use only with an account and vehicle **you own**.
- Undocumented vendor API — no warranty; can break if CarLinko changes backends.
- Secrets belong in Home Assistant’s config entry (or a gitignored `.env` for the
  optional CLI). Do not run this as a multi-user public service.

## Troubleshooting

Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.carlinko: debug
```

For level guidance and conventions when changing the integration, see
[docs/logging.md](docs/logging.md). For normal use, `custom_components.carlinko: info` is enough.

To reduce noise, raise only the REST or WebSocket module (for example
`custom_components.carlinko.managers.ws_client: warning` and
`custom_components.carlinko.managers.api_client: info`) while keeping the
integration at `info`.

Then open an issue with logs **and** diagnostic details (Settings → Devices &
services → CarLinko → ⋮ → Download diagnostics). If auth fails after a long idle
period or after changing your CarLinko password, use **Re-authenticate** on the
integration entry.

## Dev without Home Assistant

Optional CLI harness (`engine/entrypoint.py`) that mounts the same HA-free
`managers/` + `models/` packages and logs entity value changes on stdout:

```bash
pip install -r requirements.txt
cp .env.example .env
mkdir -p data && cp config.example.json data/config.json
# optional: set vehicles.<id>.device_sn; multi-car needs --vehicle-id
cd engine && python entrypoint.py
# python entrypoint.py --vehicle-id 15585
# python entrypoint.py --locate --vehicle-id 15585
```

## Repo layout

| Path                                                         | Role                                                        |
| ------------------------------------------------------------ | ----------------------------------------------------------- |
| [`custom_components/carlinko/`](custom_components/carlinko/) | HA integration (`common` / `managers` / `models` / `brand`) |
| [`engine/`](engine/)                                         | Dev harness (single-file CLI, no HA)                        |
| [`www/`](www/)                                               | Brand icon/logo copy for README (same as `brand/`)          |
| [`docs/`](docs/)                                             | API map, opcodes, logging standard                          |

## Docs

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) (pre-commit + [CI](.github/workflows/ci.yml))
- [Control opcodes](docs/control-opcodes.md)
- [API / blob map](docs/api-map.md)
- [Logging standard](docs/logging.md) (development)
- [Security](SECURITY.md)

## License

See [LICENSE](LICENSE).
