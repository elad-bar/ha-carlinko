# CarLinko

Home Assistant custom integration for Chery Group / CarLinko connected cars
(BEV and PHEV). Live state over the CarLinko WebSocket (`cloud_push`), with
remote controls through the official cloud API.

Not affiliated with Jaecoo, Chery, or CarLinko.

Based on
[GodrezJr2/j5-ev-dashboard](https://github.com/GodrezJr2/j5-ev-dashboard),
used as the starting point for this custom component.

## Requirements

- Home Assistant (see `hacs.json` for the tested version)
- A CarLinko app account with a paired vehicle you own
- Network access from Home Assistant to CarLinko cloud services

## Install

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories  
   Add this repo as type **Integration** (until it is listed in HACS).
2. Install **CarLinko**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **CarLinko**.
4. Enter email, password, and region (e.g. `sea`).

### Manual

Copy `custom_components/carlinko/` into
`<config>/custom_components/carlinko/`, restart, then add the integration.

## Configuration

| Field    | Required | Description                                      |
|----------|----------|--------------------------------------------------|
| Email    | yes      | CarLinko account email                           |
| Password | yes      | CarLinko account password                        |
| Region   | no       | Region code used by the app (default / example: `sea`) |

On submit, the integration logs in against CarLinko and stores the session.
If the token goes stale, Home Assistant prompts for **re-authentication**
(password only; email/region kept).

| Error                     | Meaning                          |
|---------------------------|----------------------------------|
| Invalid email or password | Auth rejected                    |
| Could not reach CarLinko  | Network / upstream failure       |
| Unexpected error          | See logs                         |
| Already configured        | Same account already added       |

## Behaviour

- Push updates over the CarLinko WebSocket (`iot_class: cloud_push`).
- Entities come from the HA-free catalog in
  [`models/entity_specs.py`](custom_components/carlinko/models/entity_specs.py).
- PHEV, direct TPMS, and capability-gated controls appear when the car reports
  them; entities are added/removed as that set changes.
- Entities go unavailable after ~40 minutes without a frame.
- Cost knobs (`tariff`, `petrol_price`, `petrol_kml`) persist in HA storage.
- Remote actions are real cloud actuation — use only on a car you own.

## Entities (overview)

| Platform        | Examples                                      |
|-----------------|-----------------------------------------------|
| Sensor          | Battery, range, odometer, charge power, tyres |
| Binary sensor   | Charging, online, doors, seat heat/vent       |
| Lock / climate  | Door lock, climate                            |
| Cover           | Windows, sunroof, liftgate                    |
| Switch / select | Engine, defog, purify, seat heat/vent, gear   |
| Button          | Find car, stop charging, quick cool/heat      |
| Number          | Charging tariff, petrol price / economy       |

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

| Path | Role |
|------|------|
| [`custom_components/carlinko/`](custom_components/carlinko/) | HA integration (`common` / `managers` / `models`) |
| [`engine/`](engine/) | Dev harness (single-file CLI, no HA) |
| [`docs/`](docs/) | API map, opcodes |

## Docs

- [Changelog](CHANGELOG.md)
- [TODO vs dolphin-robot](TODO.md)
- [Contributing](CONTRIBUTING.md) (pre-commit + [CI](.github/workflows/ci.yml))
- [Control opcodes](docs/control-opcodes.md)
- [API / blob map](docs/api-map.md)
- [Security](SECURITY.md)

## License

See [LICENSE](LICENSE).
