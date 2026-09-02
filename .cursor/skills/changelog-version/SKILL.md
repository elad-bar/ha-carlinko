---
name: changelog-version
description: >-
  Syncs integration version and CHANGELOG.md with the latest GitHub release.
  Increments the manifest patch when it already matches that release; otherwise
  only appends changelog notes. Use when adding a feature, fixing a bug, or
  when the user asks to bump version, update the changelog, or prepare a
  release note.
---

# Changelog and version

Do this after the code change. Do **not** create git tags or `gh release create` — CI publishes on `main` / `master`. See [docs/standards/ci.md](../../../docs/standards/ci.md).

## Version

1. Read `version` from [`custom_components/carlinko/manifest.json`](../../../custom_components/carlinko/manifest.json).
2. Read the latest GitHub **release** (not only local tags), e.g. `gh release list --limit 1`. Strip a leading `v`.
3. **If there is no GitHub release:** leave the manifest as-is.
4. **If latest release equals the manifest:** that version is already shipped. Increment the **patch** (`0.1.7` → `0.1.8`). Write the new version into `manifest.json`. Add a new `## [x.y.z] - YYYY-MM-DD` section at the top of [`CHANGELOG.md`](../../../CHANGELOG.md) (Keep a Changelog; today’s date).
5. **If latest release does not equal the manifest** (manifest already ahead): do **not** bump. Append this change under the existing `## [manifest version]` section.

Stacked PRs on the same unreleased version: first bump wins; later PRs only append bullets.

## Changelog bullet

Always add a bullet for the work (feature **and** bug). Use:

- `### Added` — new capability
- `### Changed` — behavior or internals the user/operator should know
- `### Fixed` — bug

Do not rewrite dates on older sections. Do not duplicate an existing bullet.

## Verify

`pytest tests/test_changelog_release.py` — the manifest version must have a section with Added, Changed, or Fixed.

When this skill is used **alone** (not from add-feature / fix-bug): `pre-commit run --all-files` from the repo root; fix failures and re-run until clean. Do not skip hooks. Parent skills already run that loop at the end — do not run it three times in one change.
