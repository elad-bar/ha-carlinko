# Contributing

Thanks for taking a look. Contributions — especially from people with **other CarLinko cars,
regions, or firmware** — are very welcome.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Pull requests
get a [template](.github/PULL_REQUEST_TEMPLATE.md); *which car you validated against* and
*confirmed vs inferred* matter most, because wrong telemetry silently lies about the vehicle.

## Good first contributions

- **Confirm compatibility.** Run the engine against your car and open a
  [compatibility report](https://github.com/elad-bar/ha-carlinko/issues/new?template=compatibility.md).
- **Fix a telemetry offset** (blob decode lives under
  [`custom_components/carlinko/protocol/`](custom_components/carlinko/protocol/) —
  `helpers.py` / `enrichments.py` / `consts.py`).
- **Docs** — setup friction, HA entity notes, opcode verification.

## Before you start

- Skim **[README.md](README.md)** and **[docs/api-map.md](docs/api-map.md)**.
- Run: `cd engine && python entrypoint.py` and confirm entity change logs on stdout.
- Install hooks once: `pip install -r requirements-dev.txt && pre-commit install`.
  Hooks run on commit (black, flake8, isort, bandit, yamllint, prettier, etc.).
  To run everything against the tree: `pre-commit run --all-files`.
  Pull requests also run [CI](.github/workflows/ci.yml) (pre-commit, hassfest, HACS, pytest).

## Pull requests

1. Keep changes focused — one feature/fix per PR.
2. Runtime pip deps live in [`requirements.txt`](requirements.txt)
   (`aiohttp`, `python-dotenv`, `homeassistant` for local typing / IDE).
   Protocol code under `custom_components/carlinko/protocol/` must stay free of
   `homeassistant` imports. Test-only deps (including `pre-commit`) are in
   `requirements-dev.txt`.
3. **Never** include `.env`, `config.json`, tokens, API keys, VIN or plate in a commit,
   screenshot, or log paste.
4. If you touch telemetry decoding, say which car/region you validated against.

## Ground rules

- Be honest about accuracy. Mark assumptions as assumptions.
- Reverse-engineering for **personal, interoperability** use only. Don't attack CarLinko's
  infrastructure, scrape other users' data, or abuse the API at scale.

Questions? Open a [Discussion](https://github.com/elad-bar/ha-carlinko/discussions).
