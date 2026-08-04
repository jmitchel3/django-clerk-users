# Release v0.4.0

- Kanbanlan: `KBL-TLG7TSCGV5HUBNLFWDN34OWXPI`
- Canonical home: `github`
- Canonical request: [#18](https://github.com/jmitchel3/django-clerk-users/issues/18)

## Request

Outcome: publish django-clerk-users 0.4.0 from the current main branch after release metadata, full verification, and review. Acceptance: pyproject and lock metadata report 0.4.0; CHANGELOG rolls Unreleased into a dated 0.4.0 section; release PR passes CI and merges to main; annotated v0.4.0 tag triggers the Release workflow; PyPI serves 0.4.0.

## Decisions

- **Release 0.4.0 rather than 0.3.5.** The staged changes include a deliberate
  breaking change: `clerk-backend-api` is no longer installed by default and
  the built-in thin REST client becomes the default backend. A minor bump is
  the appropriate compatibility signal while the package remains pre-1.0.
- **Release the verified `main` line without absorbing later queued work.** The
  release branch starts at `15207ac8790fb2f07eaee63a9f7e4f68a93cd004`, whose
  completed main-branch CI run succeeded. Workflow-modernization request #19
  and coverage request #20 were captured after this release request and remain
  outside the release scope.
- **Publish only from the reviewed release commit.** The version/changelog
  change is delivered through a pull request to `main`; an annotated `v0.4.0`
  tag on the resulting main commit triggers the repository's trusted PyPI
  publishing workflow. No local artifact is uploaded directly.

## Verification

- Release preflight:
  - PyPI reported `0.3.4` as the latest published version; no `0.4.0` release
    existed.
  - No `v0.4.0` tag or open pull request existed.
  - Main SHA `15207ac8790fb2f07eaee63a9f7e4f68a93cd004` passed GitHub Actions CI:
    <https://github.com/jmitchel3/django-clerk-users/actions/runs/30934286149>.
- `uv lock --check` — resolved 67 packages without changing the lockfile.
- `uv run python -m pip check` — no broken requirements.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 102 files already formatted.
- `uv run python -m django makemigrations --settings=tests.settings --check
  --dry-run` — no model changes detected. The expected missing-test-secret
  warning was reported.
- `uv run python -m pytest -q` — 653 passed, 28 skipped.
- `uv build` — built the `0.4.0` sdist and wheel.
- `GITHUB_REF_TYPE=tag GITHUB_REF_NAME=v0.4.0 uv run python
  scripts/check_dist.py` — both artifacts and tag/version agreement passed.
- Installed `dist/django_clerk_users-0.4.0-py3-none-any.whl`, then ran
  `scripts/smoke_installed_wheel.py` — installed-wheel smoke passed for 0.4.0.
- `scripts/live_clerk_smoke.py --allow-missing-env` — correctly reported that
  local Clerk/Svix release credentials were unavailable; the tag workflow runs
  the same check in the protected `release` environment before PyPI upload.
- `uv run pre-commit run --files CHANGELOG.md pyproject.toml uv.lock
  docs/kanbanlan/requests/KBL-TLG7TSCGV5HUBNLFWDN34OWXPI.md` — passed.

## Delivered result

The release change sets the project and lockfile versions to `0.4.0`, converts
the staged changelog into the dated 0.4.0 release notes, and records the release
decision and evidence here. Publication is performed by tagging the reviewed,
CI-verified main commit; the repository release workflow reruns the supported
Python matrix and publishes through PyPI trusted publishing only after every
release job succeeds.
