# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-clerk-users is a Django package for integrating Clerk authentication with Django. It provides:

- Custom user model (`ClerkUser`) with Clerk integration
- JWT token validation via Clerk SDK
- Session-based authentication middleware (validates once, caches in session)
- Webhook handling with Svix signature verification
- Optional organizations support (separate sub-app)
- Django REST Framework authentication (optional)

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run python -m pytest

# Run a single test
uv run python -m pytest tests/test_import.py::TestModels::test_clerk_user_model -v

# Run tests with coverage across Python versions (3.12, 3.13, 3.14)
uv run tox

# Run pre-commit hooks
uv run pre-commit run --all-files

# Install package in development mode
uv pip install -e .
```

## Code Architecture

### Package Structure

```
src/django_clerk_users/
├── models.py              # AbstractClerkUser, ClerkUser, ClerkUserManager
├── settings.py            # Package settings (CLERK_* settings)
├── client.py              # Clerk SDK client singleton
├── authentication/        # Auth backends and token utilities
│   ├── backends.py        # ClerkBackend (Django auth)
│   ├── drf.py             # ClerkAuthentication (DRF, optional)
│   └── utils.py           # Token validation, user creation
├── middleware/
│   └── auth.py            # ClerkAuthMiddleware
├── webhooks/
│   ├── views.py           # Webhook endpoint
│   ├── security.py        # Svix verification
│   ├── handlers.py        # Event handlers
│   └── signals.py         # Django signals for extensibility
├── organizations/         # Optional sub-app
│   ├── models.py          # Organization, OrganizationMember, OrganizationInvitation
│   ├── middleware.py      # ClerkOrganizationMiddleware
│   └── webhooks.py        # Organization event handlers
├── decorators.py          # @clerk_user_required, @clerk_org_required
├── caching.py             # User/org caching utilities
├── utils.py               # update_or_create_clerk_user, etc.
└── management/commands/
    ├── sync_clerk_users.py
    ├── sync_clerk_organizations.py
    └── migrate_users_to_clerk.py
```

### Key Patterns

1. **Session-based optimization**: JWT validated once, then cached in Django session. Re-validates every 5 minutes.

2. **Lazy imports**: `__init__.py` uses `__getattr__` to avoid loading models before Django apps are ready.

3. **Swappable user model**: Provides both `AbstractClerkUser` (for custom models) and `ClerkUser` (concrete).

4. **Signal-based webhooks**: Handlers emit signals (`clerk_user_created`, etc.) for extensibility.

5. **Optional DRF**: Install with `uv pip install django-clerk-users[drf]` for DRF authentication.

## Configuration

```python
# Required settings
CLERK_SECRET_KEY = env("CLERK_SECRET_KEY")
CLERK_WEBHOOK_SIGNING_KEY = env("CLERK_WEBHOOK_SIGNING_KEY")
CLERK_FRONTEND_HOSTS = ["https://myapp.com"]

# Optional settings
CLERK_SESSION_REVALIDATION_SECONDS = 300  # 5 minutes
CLERK_CACHE_TIMEOUT = 300  # 5 minutes
```

## Testing

- Tests use pytest-django with settings in `tests/settings.py`
- Tests use mock Clerk credentials (no actual API calls)
- Run `uv run python -m pytest -v` for verbose output

## Releasing

Releases are automated via GitHub Actions (`.github/workflows/release.yaml`).

To release a new version:

1. Claim a release request and use its dedicated branch and worktree.
2. Update `pyproject.toml`, refresh `uv.lock`, and add dated release notes to
   `CHANGELOG.md`. Record validation in the request's durable record.
3. Open a pull request to `main`, wait for its checks, and merge it.
4. Verify CI and the `Live Clerk Smoke` workflow on the resulting main commit.
5. Create an annotated `vX.Y.Z` tag on that verified commit and push the tag.
6. Verify the release workflow succeeds and PyPI serves the expected artifacts.

The workflow will:
- Run tests on Python 3.12, 3.13, 3.14
- Build the package
- Publish to PyPI (using trusted publishing)

<!-- kanbanlan:start -->
## Request Coordination Workflow

Requests live on [jmitchel3 Project 13](https://github.com/users/jmitchel3/projects/13).
Details: `docs/workflow/kanbanlan.md`.

- Before coding, run `kanbanlan start <ref-or-title> --touchpoints "..."` and
  work only in the worktree it prints.
- If `start` refuses, or lists another claim that conflicts semantically with
  this work, stop and ask.
- One card per session. Do not expand its scope into another outcome.
- Write decisions and verification in the pull request body.
- When the work is ready, run `kanbanlan done` (it opens or finds the pull
  request). `kanbanlan drop` abandons the card.
- Status questions are read-only. "Remember this" means `kanbanlan admin capture`.
<!-- kanbanlan:end -->
