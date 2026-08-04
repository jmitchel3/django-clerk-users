# Modernize GitHub Actions workflows

- Kanbanlan: `KBL-SEYO66JZ3JFJLL4X73VZKG6P2E`
- Canonical home: `github`
- Canonical request: [#19](https://github.com/jmitchel3/django-clerk-users/issues/19)

## Request

Outcome: update GitHub Actions workflows to address current runner warnings and
deprecated action/runtime features.

Acceptance: warning-producing actions and deprecated workflow features are
upgraded or replaced across all workflows; workflow syntax and project
verification pass; changes are delivered in a dedicated reviewable pull
request.

## Decisions

- Upgrade every JavaScript action identified by the latest CI annotations from
  Node.js 20 to its current Node.js 24 release line.
- Use `astral-sh/setup-uv@v9.0.0`, an immutable release tag. Setup-uv stopped
  publishing moving major and minor tags in v8.
- Keep setup-uv caching enabled. The cache restore/save warnings in the sampled
  run were GitHub service errors, while the current cache inputs remain valid.

## Verification

- `/private/tmp/actionlint-kbl-seyo66-20260804/actionlint -color
  .github/workflows/*.yaml` using actionlint 1.7.12 — clean.
- `uv run pre-commit run --files <four workflows> <request record>` — all
  applicable hooks passed.
- `git diff --check` — clean.
- Inspected the referenced upstream action manifests: each upgraded JavaScript
  action declares the Node.js 24 runtime, and every retained input is supported
  by its target version.

## Delivered result

All four workflows now use current Node.js 24 action releases:

- `actions/checkout@v7`
- `actions/setup-python@v7`
- `actions/upload-artifact@v7`
- `actions/download-artifact@v8`
- `astral-sh/setup-uv@v9.0.0`

The CI, release, scheduled cryptography watch, and manually dispatched live
smoke workflows no longer reference the Node.js 20 actions named in GitHub's
deprecation annotations. No workflow behavior or cache policy was otherwise
changed.
