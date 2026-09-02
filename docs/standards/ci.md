# CI standards

Workflow: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). Do not copy this file into PRs as documentation — change the YAML when behavior must change, and keep this page as **intent**.

## Triggers

- Push to `main`, `master`, or `develop`
- Pull requests
- Weekly cron (Monday 06:00 UTC)
- `workflow_dispatch`

Concurrency cancels in-progress runs on the same ref.

## Jobs that must stay

| Job            | Purpose                                                                                |
| -------------- | -------------------------------------------------------------------------------------- |
| **pre-commit** | Same hooks as local (`pre-commit run --all-files`) on Python 3.13                      |
| **hassfest**   | Home Assistant integration validation                                                  |
| **hacs**       | HACS action, `category: integration`                                                   |
| **pytest**     | `pip install -r requirements.txt -r requirements-dev.txt` then `pytest` on Python 3.13 |

Do not add a CI job unless it is required for HACS/HA or a hard project invariant. Do not skip hooks (`--no-verify`) or drop a required job to land a PR.

## Release

The **release** job runs only on **push** to `main` or `master`, and only after the four jobs above succeed.

- Version comes from [`custom_components/carlinko/manifest.json`](../../custom_components/carlinko/manifest.json).
- Notes come from the matching section of [`CHANGELOG.md`](../../CHANGELOG.md) via `scripts/extract_changelog_section.py`.
- Tag is `v<version>`. Tag create and `gh release create` are **idempotent** (skip if the tag/release already exists).

Do not hand-create release tags that fight this workflow. Before bumping the manifest: add a Keep a Changelog section and run `pytest tests/test_changelog_release.py`. See [CONTRIBUTING.md](../../CONTRIBUTING.md) (Releases).

Optional assets (demo video, etc.) can be uploaded on GitHub after CI publishes the release.

## Local equivalent

```bash
pip install -r requirements-dev.txt
pre-commit install
pre-commit run --all-files
pytest
```

HA plugin tests need Linux (`fcntl`). Native Windows skips the modules listed in [testing.md](testing.md); WSL or a Linux container runs the full suite. CI remains the authority.
