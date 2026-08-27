# Engine — CarLinko live stream (dev harness)

Thin CLI that imports the protocol package under
[`custom_components/carlinko/protocol/`](../custom_components/carlinko/protocol/).
No SQLite, no HTTP dashboard. Native Home Assistant integration is the product surface.

## Run

```bash
# From repo root:
cp .env.example .env                         # secrets
mkdir -p data && cp config.example.json data/config.json
cd engine && python entrypoint.py
```

Or:

```bash
export CARLINKO_DATA=/path/to/data           # must contain config.json
# CARLINKO_EMAIL / PASSWORD / REGION in env or .env
cd engine && python entrypoint.py
```

Requires packages from the repo `requirements.txt` (`aiohttp`, `python-dotenv`).
The entrypoint registers `custom_components/carlinko/protocol` as top-level
`protocol` (via `protocol_path.py`) so the engine never imports the Home
Assistant integration package and never shadows stdlib modules.

Logging defaults to **INFO** on stdout. Set `CARLINKO_LOG_LEVEL=DEBUG` or `DEBUG=true`
in `.env` for per-frame WebSocket lines from `ws_client`.

## What it does

1. Logs in via `ApiClient` (token saved to `config.json`)
2. Streams the CarLinko realtime WebSocket
3. Decodes each status frame into live state
4. Logs entity value deltas via `EntityPublisher` when values change

## Files (engine/)

| File | Role |
|------|------|
| `entrypoint.py` | Dev CLI — wires config, API, state, WS, entity change logs |
| `protocol_path.py` | Registers HA-free `protocol` package for engine imports |
| `log_setup.py` | `configure_logging()` — stdout handler, env log level |
| `entity_publisher.py` | Dev-only delta logger over `EntityValueResolver` |

## Protocol (canonical)

All protocol / decode / entity catalog code lives in
[`custom_components/carlinko/protocol/`](../custom_components/carlinko/protocol/):

`api_client`, `ws_client`, `vehicle_state`, `blob_fields`, `enrichments`, `helpers`,
`consts`, `entity_specs`, `entity_values`, `config_manager`, `config_adapter`.
