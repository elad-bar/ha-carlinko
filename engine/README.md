# Engine — CarLinko live stream (dev harness)

Single-file CLI that mounts HA-free `carlinko.managers` / `carlinko.models`
without loading the Home Assistant integration. Native HA is the product surface.

## Run

```bash
# From repo root:
cp .env.example .env                         # secrets
mkdir -p data && cp config.example.json data/config.json
cd engine && python entrypoint.py
cd engine && python entrypoint.py --locate        # one-shot map locate probe
cd engine && python entrypoint.py --seat-probe    # WS: seat heat/vent byte window
cd engine && python entrypoint.py --seat-test vent-rr   # opcode → blob confirm
```

Requires packages from the repo `requirements.txt` (`aiohttp`, `python-dotenv`).

Logging defaults to **INFO** on stdout. Set `CARLINKO_LOG_LEVEL=DEBUG` or `DEBUG=true`
in `.env` for verbose WebSocket lines.

## What it does

1. Logs in via `ApiClient` (token saved via `CarlinkoStore` → `config.json`)
2. Streams the CarLinko realtime WebSocket
3. Decodes each status frame into live state
4. Logs entity value deltas when values change

### `--locate`

One-shot probe of `POST /maps/deviceLocate` via `ApiClient.device_locate`.
Logs in, refreshes vehicles, prints `lat` / `lng` / `address` (or the error code),
then exits. Does not start the WS stream.

### `--seat-probe`

Same WebSocket stream as the default harness. Each frame is a snapshot of
`STATUS_BLOB_MAP` in `entrypoint.py` (app status parse: lock, seats A–D, charge,
…; indexes include the `7700` header). Unmapped bytes are `raw[n]`. First frame
logs a baseline; later frames log only keys that changed. Toggle one dash
control at a time. Confirmed offsets: [docs/api-map.md](../docs/api-map.md). Does not
write offsets into the HA decoder.

### `--seat-test`

Sends **A/C on** (`741001`) only if the blob does not already show climate/HV up
(`ac_switch=1` or `engine>=2`). Waits `--delay` seconds (default 10), sends the
seat **L2** opcode, waits for **exactly one** heat or vent family key to go
positive, then sends **off**. If this mode turned A/C on, it turns A/C off at
the end. Does **not** send engine start (`740700`).

```bash
cd engine && python entrypoint.py --seat-test vent-rr
cd engine && python entrypoint.py --seat-test heat-l --delay 0 --timeout 30
```

Ids: `heat-l` / `heat-r` / `heat-lr` / `heat-rr` / `vent-l` / `vent-r` /
`vent-lr` / `vent-rr`. Be at the car: this sends live `remoteControl`.
`vent-rr` (`741E`) moved blob byte 41; `heat-lr` (`7417`) moved byte 34. Dash confirmed rear R heat on byte 36, windshield 64, wheel 65. Cloud accepted rear opcodes with `RearVent` / `RearHeater` false.

## Layout

| Path                                   | Role                                                     |
| -------------------------------------- | -------------------------------------------------------- |
| `engine/entrypoint.py`                 | Only engine Python file — mount + CLI + delta logs       |
| `custom_components/carlinko/managers/` | API / WS / **shared** `CarlinkoStore` (+ HA coordinator) |
| `custom_components/carlinko/models/`   | Wire consts, catalog, vehicle state, exceptions          |
| `custom_components/carlinko/common/`   | HA-facing shared (consts, base entity, setup)            |
