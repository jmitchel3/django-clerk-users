# ci: let live smoke read CLERK_FRONTEND_HOSTS from synced secrets

- Kanbanlan: `KBL-FOC6LUX6ZFG73BGBZFTGCPEQBA`
- Canonical home: `github`
- Canonical request: [#42](https://github.com/jmitchel3/django-clerk-users/issues/42)

## Request

Doppler syncs Clerk settings to GitHub as repository secrets, but `.github/workflows/live-smoke.yaml` reads `CLERK_FRONTEND_HOSTS` (and `CLERK_LIVE_SMOKE_LOOKUP_EMAIL`) only from `vars.*`, so synced values never reach the job.

Outcome: the workflow prefers `secrets.*` and falls back to `vars.*`, so either source works. Every step that can hang has a timeout.

## Decisions

- `CLERK_FRONTEND_HOSTS` and `CLERK_LIVE_SMOKE_LOOKUP_EMAIL` read `secrets.*` first and fall back to `vars.*`, because Doppler's GitHub sync writes repository secrets.
- Added per-step timeouts to the install, build, and external-call steps.

## Verification

- Workflow YAML parses; pre-commit passes. Live smoke run on the merged workflow recorded in the PR.

## Delivered result

Live smoke picks up Doppler-synced frontend hosts. Follow-up outside the repo: point the Doppler GitHub sync at the `dev` config instead of `prd`.
