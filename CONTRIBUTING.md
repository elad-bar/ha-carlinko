# Contributing

Thanks for taking a look. Contributions — especially from people with **other CarLinko cars,
regions, or firmware** — are very welcome.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Pull requests
get a [template](.github/PULL_REQUEST_TEMPLATE.md); _which car you validated against_ and
_confirmed vs inferred_ matter most, because wrong telemetry silently lies about the vehicle.

## Good first contributions

- **Confirm compatibility.** Run the engine against your car and open a
  [compatibility report](https://github.com/elad-bar/ha-carlinko/issues/new?template=compatibility.md).
- **Fix a telemetry offset** (blob decode lives under
  [`custom_components/carlinko/models/`](custom_components/carlinko/models/) —
  `helpers.py` / `enrichments.py` / `consts.py`).
- **Docs** — setup friction, HA entity notes, opcode verification.
- **Translations** — polish UI strings for your language (see below).

## Translations

UI strings are in [`custom_components/carlinko/strings.json`](custom_components/carlinko/strings.json)
(English source) and [`custom_components/carlinko/translations/`](custom_components/carlinko/translations/)
(one JSON file per HA locale). Non-English files were bootstrapped with machine
translation; please open PRs to fix automotive wording, RTL phrasing, or brand
usage (**CarLinko** stays untranslated).

When you add or change entities in [`entity_specs.py`](custom_components/carlinko/models/entity_specs.py):

1. Update `strings.json` and `translations/en.json` together.
2. Fill **new keys only** in locale files (edit by hand or run the generator — see below).
3. Run `pytest tests/test_translations.py`.

To fill **missing** strings from English locally (optional, needs network; from
[`requirements-dev.txt`](requirements-dev.txt)):

```bash
pip install -r requirements-dev.txt
python scripts/generate_translations.py
python scripts/fix_translation_placeholders.py
prettier --write custom_components/carlinko/translations/*.json
pytest tests/test_translations.py
```

The generator **does not overwrite** existing non-empty strings in a locale file, so
contributor improvements are kept. It only machine-translates keys that are missing
or empty. Use `--force` to re-translate everything (destructive — avoid on main).

Do not commit API keys. Review safety-related labels (lock, charging stop, tyres)
after bulk generation.

## Before you start

- Skim **[README.md](README.md)** and **[docs/api-map.md](docs/api-map.md)**.
- Run: `cd engine && python entrypoint.py` and confirm entity change logs on stdout.
- Install hooks once: `pip install -r requirements-dev.txt && pre-commit install`.
  Hooks run on commit (black, flake8, isort, bandit, yamllint, prettier, etc.).
  To run everything against the tree: `pre-commit run --all-files`.
  Pull requests also run [CI](.github/workflows/ci.yml) (pre-commit, hassfest, HACS, pytest).

## Releases

Version lives in [`custom_components/carlinko/manifest.json`](custom_components/carlinko/manifest.json).
When merging to `main` / `master`, CI runs the same checks, then (on success) creates `v<version>`
if that tag is missing and publishes a [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github)
whose notes come from the matching section in [`CHANGELOG.md`](CHANGELOG.md).

Before bumping the manifest for a release:

1. Add a `## [x.y.z] - YYYY-MM-DD` section to `CHANGELOG.md` (Keep a Changelog style).
2. Run `pytest tests/test_changelog_release.py` — it fails if the manifest version has no changelog entry.

Optional release assets (e.g. demo video) can be uploaded manually to the release on GitHub after CI publishes it.

## Pull requests

1. Keep changes focused — one feature/fix per PR.
2. Runtime pip deps live in [`requirements.txt`](requirements.txt)
   (`aiohttp`, `python-dotenv`, `homeassistant` for local typing / IDE).
   HA-free code under `custom_components/carlinko/models/` and the API/WS clients in
   `managers/` must stay free of `homeassistant` imports. Test-only deps (including
   `pre-commit`) are in `requirements-dev.txt`.
3. **Never** include `.env`, `config.json`, tokens, API keys, VIN or plate in a commit,
   screenshot, or log paste.
4. If you touch telemetry decoding, say which car/region you validated against.

## Ground rules

- Be honest about accuracy. Mark assumptions as assumptions.
- Reverse-engineering for **personal, interoperability** use only. Don't attack CarLinko's
  infrastructure, scrape other users' data, or abuse the API at scale.

Questions? Open a [Discussion](https://github.com/elad-bar/ha-carlinko/discussions).
