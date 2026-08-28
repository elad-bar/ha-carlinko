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
(password only; email/region kept). Use **Reconfigure** to change password and
region without removing the integration.

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
| Region                        | `sea`            | Cloud region (one of the known codes above)            |
| Stream backstop (seconds)     | `20`             | WS keepalive / re-request interval                     |
| Availability window (seconds) | `2400` (~40 min) | Entities go unavailable if no frame within this window |

## Behaviour

- Push updates over the CarLinko WebSocket (`iot_class: cloud_push`).
- Entities come from the HA-free catalog in
  [`models/entity_specs.py`](custom_components/carlinko/models/entity_specs.py).
- PHEV, direct TPMS, and capability-gated controls appear when the car reports
  them; entities are added/removed as that set changes.
- Cost knobs (`tariff`, `petrol_price`, `petrol_kml`) persist in HA storage.
- Currency for monetary amounts comes from Home Assistant **Settings → General**;
  CarLinko does not store a currency code or convert amounts on currency change.

## Known limitations

- Undocumented vendor API — no warranty; backends can change without notice.
- Entities are capability-gated: only features the car reports are created.
- Remote actions are real cloud actuation — use only on a car you own.
- API does not expose OEM brand, `sw_version` / `hw_version`, or a useful
  `configuration_url`.
- Entities go unavailable after the availability window without a fresh frame
  (default ~40 minutes).
- No `device_tracker` yet (coordinates not wired).

## Entities (overview)

| Platform        | Examples                                             |
| --------------- | ---------------------------------------------------- |
| Sensor          | Battery, range, odometer, speed, charge power, tyres |
| Binary sensor   | Charging, online, doors, seat heat/vent              |
| Lock / climate  | Door lock, climate                                   |
| Cover           | Windows, sunroof, liftgate                           |
| Switch / select | Engine, defog, purify, seat heat/vent, gear          |
| Button          | Find car, stop charging, quick cool/heat             |
| Number          | Charging tariff, petrol price / economy              |

Full catalog and opcodes: [`entity_specs.py`](custom_components/carlinko/models/entity_specs.py),
[`docs/control-opcodes.md`](docs/control-opcodes.md).

File a [compatibility report](https://github.com/elad-bar/ha-carlinko/issues/new?template=compatibility.md)
if you try another model.

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

Then open an issue with logs **and** diagnostic details (Settings → Devices &
services → CarLinko → ⋮ → Download diagnostics). If auth fails after a long idle
period or after changing your CarLinko password, use **Reconfigure /
Reauthenticate** on the integration entry.

## Dev without Home Assistant

Optional CLI harness (`engine/entrypoint.py`) that mounts the same HA-free
`managers/` + `models/` packages and logs entity value changes on stdout:

```bash
pip install -r requirements.txt
cp .env.example .env
mkdir -p data && cp config.example.json data/config.json
# set vehicle_id / device_sn in data/config.json
cd engine && python entrypoint.py
```

## Repo layout

| Path                                                         | Role                                                        |
| ------------------------------------------------------------ | ----------------------------------------------------------- |
| [`custom_components/carlinko/`](custom_components/carlinko/) | HA integration (`common` / `managers` / `models` / `brand`) |
| [`engine/`](engine/)                                         | Dev harness (single-file CLI, no HA)                        |
| [`www/`](www/)                                               | Brand icon/logo copy for README (same as `brand/`)          |
| [`docs/`](docs/)                                             | API map, opcodes                                            |

## Docs

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) (pre-commit + [CI](.github/workflows/ci.yml))
- [Control opcodes](docs/control-opcodes.md)
- [API / blob map](docs/api-map.md)
- [Security](SECURITY.md)

## License

See [LICENSE](LICENSE).
