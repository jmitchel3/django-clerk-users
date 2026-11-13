# Release django-clerk-users v0.5.1

- Kanbanlan: `KBL-PLKL35S3NRG5TJX5VRPFVZZHR4`
- Canonical home: `github`
- Canonical request: [#47](https://github.com/jmitchel3/django-clerk-users/issues/47)

## Request

Publish v0.5.1 after the three review fixes (#44 database routing, #45 source distribution recipe assets, #46 strict Authorization handling) merge. Scope: version and lock metadata, release notes, durable release verification, reviewed release PR, annotated tag, trusted PyPI publication and published artifact verification. Dependencies: #44, #45, #46. Do not start release metadata edits until those independent fixes are merged. Acceptance: relevant regressions, supported Python/Django CI matrix, artifact and installed-wheel checks, and live Clerk smoke pass; PyPI serves 0.5.1.

## Decisions

- Release from the merged fixes in main at `783ebc1842a77c80cff322d6e04a0835f3e5e567`.
  Routing, source distribution, and strict recipe changes were delivered through
  independently reviewed PRs #49, #48, and #50, respectively. All nine CI checks
  passed on each fix PR before merge.
- Keep this release request limited to version metadata, release notes, and
  publication. The dependency lock changes only the package version; dependency
  versions remain unchanged.
- Publish through the repository's trusted PyPI workflow by tagging the reviewed,
  CI-verified main commit with an annotated `v0.5.1` tag. Do not upload local
  artifacts directly.
- Run the manual Live Clerk Smoke workflow on the final main commit before
  tagging. That workflow reads the frontend hosts from the repository secret,
  matching the current secret configuration.

## Verification

- Python 3.13, Django 6.0.7, Svix 2.10.0, DRF 3.17.1: full suite **952 passed,
  21 skipped**. Optional PostgreSQL checks also run in the CI service job.
- Frozen lock consistency and `pip check` passed. Ruff lint and formatting passed
  for all 127 Python files. `makemigrations --check --dry-run` found no changes;
  only the expected placeholder-secret warning appeared in test settings.
- Built the 0.5.1 wheel and source archive. `scripts/check_dist.py` passed with
  `GITHUB_REF_TYPE=tag` and `GITHUB_REF_NAME=v0.5.1`, checking metadata, required
  recipe files, and tag/version agreement.
- Independently extracted the final source archive: **973 tests collected**;
  the session activity, DRF recipe, and release-script tests **72 passed**.
- Installed the built wheel into the isolated release environment and ran
  `scripts/smoke_installed_wheel.py`; installed-wheel imports and migration smoke
  passed for version 0.5.1.
- Release PR CI and the final main commit's live smoke are publication gates.
  The tag workflow reruns the supported Python matrix and artifact checks before
  trusted PyPI publication. Published wheel and sdist are verified afterwards.

## Delivered result

Version 0.5.1 contains instance-aware session timestamp writes and refreshes,
the recipe assets needed to run tests from a source archive, and strict recipe
rejection of supplied blank Authorization headers. The version and lock metadata
are 0.5.1, and the dated changelog documents all three fixes. Publication follows
the reviewed PR, CI, live smoke, annotated tag, and PyPI verification gates above.
