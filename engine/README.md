# Engine — CarLinko live stream (dev harness)

Single-file CLI that mounts HA-free `carlinko.managers` / `carlinko.models`
without loading the Home Assistant integration. Native HA is the product surface.

## Run

```bash
# From repo root:
cp .env.example .env                         # secrets
mkdir -p data && cp config.example.json data/config.json
cd engine && python entrypoint.py
```

Requires packages from the repo `requirements.txt` (`aiohttp`, `python-dotenv`).

Logging defaults to **INFO** on stdout. Set `CARLINKO_LOG_LEVEL=DEBUG` or `DEBUG=true`
in `.env` for verbose WebSocket lines.

## What it does

1. Logs in via `ApiClient` (token saved to `config.json`)
2. Streams the CarLinko realtime WebSocket
3. Decodes each status frame into live state
4. Logs entity value deltas when values change

## Layout

| Path | Role |
|------|------|
| `engine/entrypoint.py` | Only engine Python file — mount + CLI + delta logs |
| `custom_components/carlinko/managers/` | API / WS clients (+ HA coordinator / store) |
| `custom_components/carlinko/models/` | Wire consts, catalog, vehicle state, exceptions |
| `custom_components/carlinko/common/` | HA-facing shared (consts, base entity, setup) |
