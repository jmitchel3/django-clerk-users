# fix: package recipe dependencies in the source distribution

- Kanbanlan: `KBL-NTFB5IVKPBBTFEWRUHOPPFNSQI`
- Canonical home: `github`
- Canonical request: [#45](https://github.com/jmitchel3/django-clerk-users/issues/45)

## Request

The published v0.5.0 source archive includes tests that import docs/recipes assets, but omits the assets, causing pytest collection to fail. Include the recipe dependencies and make distribution checks enforce their presence. Validate collection and DRF recipe tests from an extracted built sdist. Scope: pyproject sdist configuration, scripts/check_dist.py, and artifact tests. Deliver in v0.5.1.

## Decisions

- Include the recipe directory in source distributions because the bundled tests
  import the Python recipe and read the Markdown and SQL files.
- Require the four current recipe assets and both recipe test modules in the
  distribution checker. The existing CI and release workflows already run this
  checker against built archives, so a future omission fails before publication.
- Keep wheel contents unchanged; recipe sources are only needed by the sdist's
  bundled tests and documentation.

## Verification

- `uv build` built the sdist and then the wheel from that sdist using an isolated
  cache. `scripts/check_dist.py` accepted both artifacts.
- Extracted the built sdist outside the checkout: full pytest collection succeeded
  with 938 tests collected, and the DRF recipe plus release-script tests passed
  (33 tests) under Django 5.2 with real DRF installed.
- Removed each of the four recipe assets from separate copies of the built
  archive; the distribution checker rejected every incomplete archive and named
  the missing file.
- Ruff lint and formatting checks passed for the changed script; `git diff
  --check` passed.

## Delivered result

Source distributions now include the recipe dependencies needed to collect and
run their bundled tests. Existing artifact validation enforces their presence.
The fix is prepared for the separately coordinated v0.5.1 release.
