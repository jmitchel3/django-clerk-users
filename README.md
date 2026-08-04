# Django Clerk Users

Integrate [Clerk](https://clerk.com) authentication with Django.

> **Production note:** Pin versions and review release notes before upgrading
> between minor versions.

## Features

- Custom user model (`ClerkUser`) with Clerk integration
- JWT token validation via Clerk SDK
- Session-based authentication middleware (validates once, caches in session)
- Webhook handling with Svix signature verification
- Optional organizations support (separate sub-app)
- Django REST Framework authentication (optional)
- Server-side Clerk SDK helpers for account provisioning and invite links

## Installation

```bash
pip install django-clerk-users
```

For Django REST Framework support:

```bash
pip install django-clerk-users[drf]
```

To use the official `clerk-backend-api` SDK for server-side API calls instead
of the built-in thin client (note that this reintroduces that SDK's
`cryptography<49` pin):

```bash
pip install django-clerk-users[sdk]
```

Use `.env.example` as a starting point for required Clerk settings in each
environment.

## Compatibility

This package supports Python 3.12 through 3.14 and Django 4.2, 5.2, and 6.0.
CI installs and tests the built wheel across those supported Django/Python
combinations and exercises the optional Django REST Framework extra.

`cryptography` is declared as `>=45` with **no upper bound**, and a default
install now has no ceiling in practice either. `clerk-backend-api` pins
`cryptography<49`, and that pin is what resolvers obey, so it lives in the
optional `[sdk]` extra rather than the base dependencies:

```bash
pip install django-clerk-users          # cryptography 50.x
pip install django-clerk-users[sdk]     # held to cryptography 48.x
```

A scheduled workflow reports where the upstream ceiling sits, and a
`py313-cryptolatest` tox environment runs the suite against the newest
`cryptography`:

```bash
uv run python scripts/check_cryptography_ceiling.py
uv run tox -e py313-cryptolatest
```

### Clerk API client backends

Server-side Clerk API calls go through a client selected by
`CLERK_CLIENT_BACKEND`:

| Value | Client | Requires | `cryptography` |
|---|---|---|---|
| `"thin"` *(default)* | Built-in REST client | nothing extra | unbounded |
| `"sdk"` | Official `clerk-backend-api` | `[sdk]` extra | capped at `<49` |

```python
# settings.py — only needed to opt into the official SDK
CLERK_CLIENT_BACKEND = "sdk"
```

Selection is **by setting only, never by what happens to be installed**.
`get_clerk_client()` is public API, so picking an implementation based on
importability would make response models, error types, retries, and available
methods depend on the environment, and would silently restore the
`cryptography` ceiling for anyone who acquired `clerk-backend-api` as a
transitive dependency. Setting `CLERK_CLIENT_BACKEND = "sdk"` without
installing the extra raises `ClerkConfigurationError` rather than falling back.

Session token verification never uses the SDK on either backend.

## Quick Start

### 1. Add to installed apps

```python
INSTALLED_APPS = [
    # ...
    "django_clerk_users",
    # Optional: for organization support
    # "django_clerk_users.organizations",
]
```

### 2. Configure settings

```python
# Required
CLERK_SECRET_KEY = "sk_live_..."  # From Clerk Dashboard
CLERK_WEBHOOK_SIGNING_KEY = "whsec_..."  # From Clerk Webhooks
CLERK_FRONTEND_HOSTS = ["https://your-app.com"]  # Your frontend URLs

# Optional
CLERK_SESSION_REVALIDATION_SECONDS = 300  # Re-validate JWT every 5 minutes
CLERK_CACHE_TIMEOUT = 300  # Cache timeout for user lookups
```

### 3. Set the user model

```python
AUTH_USER_MODEL = "django_clerk_users.ClerkUser"
```

Or extend the abstract model for custom fields:

```python
# myapp/models.py
from django.db import models
from django_clerk_users.models import AbstractClerkUser


class CustomUser(AbstractClerkUser):
    company = models.CharField(max_length=255, blank=True)

    class Meta(AbstractClerkUser.Meta):
        swappable = "AUTH_USER_MODEL"


# settings.py
AUTH_USER_MODEL = "myapp.CustomUser"
```

### 4. Add middleware

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_clerk_users.middleware.ClerkAuthMiddleware",  # Add after AuthenticationMiddleware
    # ...
]
```

### 5. Add authentication backend

**For Clerk-only authentication:**

```python
AUTHENTICATION_BACKENDS = [
    "django_clerk_users.authentication.ClerkBackend",
]
```

**For hybrid authentication (Clerk + Django admin):**

If you want to support both Clerk authentication (JWT) and traditional Django admin login (username/password), use both backends:

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # For Django admin
    "django_clerk_users.authentication.ClerkBackend",  # For Clerk JWT
]
```

This allows:
- Admin users to log in via Django admin with username/password
- Frontend users to authenticate via Clerk JWT tokens
- The middleware automatically detects which authentication method was used

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Configure webhooks

Add the webhook URL to your `urls.py`:

```python
from django_clerk_users.webhooks import clerk_webhook_view

urlpatterns = [
    # ...
    path("webhooks/clerk/", clerk_webhook_view, name="clerk_webhook"),
]
```

Then configure your Clerk Dashboard to send webhooks to `https://your-app.com/webhooks/clerk/`.

For additional Clerk webhook endpoints, each endpoint gets its own Svix signing
secret. Use the package verifier with an endpoint-specific setting:

```python
from django.http import JsonResponse
from django_clerk_users.webhooks import clerk_webhook_required


@clerk_webhook_required(signing_key_setting="CLERK_ACTIVATION_WEBHOOK_SIGNING_KEY")
def activation_webhook(request):
    data = request.clerk_webhook_data
    return JsonResponse({"ok": True, "type": data.get("type")})
```

### 8. Create admin users (for hybrid authentication)

If you're using hybrid authentication, create an admin user for Django admin access:

```bash
python manage.py createsuperuser
```

This creates a user with:
- Username/password authentication (for Django admin)
- No `clerk_id` (since they're not Clerk users)
- Access to Django admin panel

Note: Regular Clerk users are created automatically via webhooks when they sign up through your frontend.

## Usage

### Accessing the user in views

```python
def my_view(request):
    if request.user.is_authenticated:
        # Access Clerk user attributes
        print(request.user.clerk_id)
        print(request.user.email)
        print(request.user.full_name)

        # Access organization (if using organizations)
        print(request.org)  # Organization ID from JWT
```

### Decorators

```python
from django_clerk_users.decorators import clerk_user_required


@clerk_user_required
def protected_view(request):
    # Only authenticated Clerk users can access
    return HttpResponse(f"Hello, {request.user.email}")
```

### Django REST Framework

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "django_clerk_users.authentication.ClerkAuthentication",
    ],
}
```

For hybrid APIs that accept Clerk bearer tokens and Django session users, use
the combined authenticator:

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "django_clerk_users.authentication.ClerkSessionAuthentication",
    ],
}
```

`ClerkSessionAuthentication` checks `Authorization: Bearer ...` with Clerk first.
Requests without a bearer token fall back to Django session authentication.
Bearer token failures are not hidden by the session fallback.

### Server-side Clerk operations

For backend flows that create accounts outside Clerk's hosted sign-up UI, use the
server API helpers instead of hand-writing Clerk SDK calls in each Django app:

```python
from django_clerk_users.server_api import provision_clerk_user_access_link


result = provision_clerk_user_access_link(
    "invitee@example.com",
    "https://app.example.com/sign-in",
    first_name="Ada",
    public_metadata={"invite_type": "staff"},
    expires_in_seconds=7 * 24 * 3600,
    auto_username=True,  # useful when the Clerk instance requires usernames
)

if result["access_link"]:
    send_invite_email(result["access_link"])
```

The helpers cover common server-side tasks:

- `create_clerk_user()` creates passwordless or password-backed Clerk users.
- `create_clerk_sign_in_token()` and `create_clerk_sign_in_link()` mint one-time
  access links using Clerk's `__clerk_ticket` flow.
- `get_clerk_user_by_email()`, `set_clerk_user_email()`, and
  `update_clerk_user_public_metadata()` keep Django profile workflows in sync
  with Clerk.
- `revoke_clerk_user_sessions()`, `send_clerk_invitation()`, and
  `revoke_clerk_invitation()` wrap common account-management operations.

When `CLERK_SECRET_KEY` is missing or set to a documented local placeholder
(`abc123`, `sk_test_mock_secret_key`, or `sk_live_replace_me`), creation helpers
return `{"no_key": True}` and mutation helpers no-op with a falsey result.

## Hybrid Authentication (Clerk + Django Admin)

The package supports hybrid authentication, allowing you to use both Clerk (JWT-based) authentication for your frontend users and traditional Django admin authentication for internal staff.

### How it works

1. **Frontend users**: Authenticate via Clerk JWT tokens (handled by `ClerkAuthMiddleware`)
2. **Admin users**: Authenticate via username/password (handled by Django's `ModelBackend`)
3. The middleware automatically detects which authentication method was used and respects existing sessions

### Configuration

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # For Django admin
    "django_clerk_users.authentication.ClerkBackend",  # For Clerk JWT
]
```

### Creating admin users

Admin users don't need a `clerk_id` (it's optional in hybrid mode):

```bash
python manage.py createsuperuser
# Email: admin@example.com
# Password: ********
```

This creates a user with:
- Username/password authentication (no Clerk integration)
- Access to Django admin panel at `/admin/`
- Standard Django permissions (is_staff, is_superuser)

### Session handling

- **Django admin sessions**: Traditional session cookies (set by Django's auth system)
- **Clerk sessions**: JWT validated once, then cached in session with `last_clerk_check` marker
- The middleware checks for `last_clerk_check` to distinguish between the two types

### Use cases

This is particularly useful when:
- Your admin panel is on a different domain than your frontend
- You want internal staff to access Django admin without Clerk accounts
- You need traditional Django auth features (permissions, groups, etc.)
- You're migrating from Django auth to Clerk gradually

### Claim and conversion flows

Some Django apps pre-create users before a Clerk signup exists. For example, a
student, invitee, or imported account may later claim a real Clerk identity. If
Clerk signs the person in before your app finishes the claim, the standard user
sync can create a fresh duplicate user for the claimed email.

Use `absorb_clerk_user_duplicate()` at the point where your app has verified the
claim and knows the historical target user:

```python
from django_clerk_users.utils import absorb_clerk_user_duplicate


def duplicate_is_fresh_shell(user):
    return (
        not user.is_staff
        and not user.is_superuser
        and not user.has_usable_password()
        # Add app-specific checks here, e.g. no memberships, roles, orders, etc.
    )


absorb_clerk_user_duplicate(
    target_user,
    email=claimed_email,
    safe_to_delete=duplicate_is_fresh_shell,
)
target_user.email = claimed_email
target_user.save(update_fields=["email"])
```

The helper moves the duplicate's `clerk_id` to the target user, deletes the
duplicate by default, and invalidates affected Clerk user cache entries. It raises
`ClerkUserMergeConflictError` instead of deleting when the duplicate is not safe
to absorb.

## Organizations (Optional)

For Clerk organization support:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_clerk_users",
    "django_clerk_users.organizations",
]

MIDDLEWARE = [
    # ...
    "django_clerk_users.middleware.ClerkAuthMiddleware",
    "django_clerk_users.organizations.middleware.ClerkOrganizationMiddleware",
]
```

## Management Commands

```bash
# Sync users from Clerk
python manage.py sync_clerk_users

# Sync organizations from Clerk
python manage.py sync_clerk_organizations

# Preview migration of existing Django users into Clerk
python manage.py migrate_users_to_clerk --source-model auth.User --all --dry-run --skip-existing

# Migrate a bounded batch and link local rows when matching Clerk users already exist
python manage.py migrate_users_to_clerk --source-model auth.User --all --limit 100 --skip-existing
```

`migrate_users_to_clerk` creates passwordless Clerk users because Django password
hashes cannot be migrated into Clerk. Existing local users with a `clerk_id`
field are linked to matching Clerk users when `--skip-existing` is used, and the
command recovers duplicate-email create races by looking up and linking the
existing Clerk user. `--created-before YYYY-MM-DD` filters on `date_joined` for
classic Django users and `created_at` for `ClerkUser`-based source models.

## Production Checklist

- Set `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_KEY`, and
  `CLERK_FRONTEND_HOSTS` from environment variables or a secret manager.
- Serve webhook endpoints over HTTPS and keep Svix signature verification
  enabled. Use a separate signing secret for each custom webhook endpoint.
- Put `ClerkAuthMiddleware` after Django's `AuthenticationMiddleware`, and put
  `ClerkOrganizationMiddleware` after `ClerkAuthMiddleware` when using
  organizations.
- Run `python manage.py check --deploy` in CI or deployment validation; the
  package registers checks for placeholder secrets, missing frontend host
  allowlists, and middleware ordering.
- Configure application logging for `django_clerk_users.*` so authentication,
  webhook, and sync failures are visible in production.
- Run `python manage.py migrate` during deploys and run sync commands with
  `--dry-run` before backfilling existing Clerk data.
- Keep the package's CI gates enabled: lockfile checks, Ruff, formatting,
  migrations, tox across supported Python versions, build verification, and
  coverage threshold enforcement.

### Release validation

Before publishing a release, run the artifact and installed-wheel checks:

```bash
uv build
uv run python scripts/check_dist.py
uv run --no-sync python -m pip install --force-reinstall --no-deps dist/django_clerk_users-*.whl
uv run --no-sync python scripts/smoke_installed_wheel.py
```

Then run the read-only live Clerk smoke check against a test/development Clerk
instance:

```bash
export CLERK_SECRET_KEY=sk_test_...
export CLERK_WEBHOOK_SIGNING_KEY=whsec_...
export CLERK_FRONTEND_HOSTS=https://app.example.com
# Optional: make the smoke check verify a known existing user lookup.
export CLERK_LIVE_SMOKE_LOOKUP_EMAIL=user@example.com

uv run python scripts/live_clerk_smoke.py
```

`scripts/live_clerk_smoke.py` performs no writes. It runs Django system checks,
calls Clerk's user list endpoint, optionally looks up an existing user by email,
and verifies a signed Svix webhook payload through the package verifier.

The tag-based release workflow runs these same artifact checks and the live
Clerk smoke check before publishing to PyPI. Configure the `release` environment
with `CLERK_SECRET_KEY` and `CLERK_WEBHOOK_SIGNING_KEY` secrets, plus optional
`CLERK_FRONTEND_HOSTS` and `CLERK_LIVE_SMOKE_LOOKUP_EMAIL` variables.
Use the `Live Clerk Smoke` workflow to run the same installed-wheel and live
Clerk checks manually before tagging a release.

## Auto-Generated Usernames

Clerk doesn't require usernames, but Django often does (for admin, URLs, etc.). This package provides options for generating usernames automatically.

### Synchronous Generation

Generate usernames inline during user creation:

```python
# settings.py
CLERK_AUTO_GENERATE_USERNAME = True  # Enable auto-generation
CLERK_AUTO_GENERATE_USERNAME_PREFIX = "user"  # Optional, default is "user"
```

Usernames are generated as `{prefix}_{uuid8}` (e.g., `user_abc12345`).

### Async Generation (Celery, django-qstash, etc.)

For high-traffic apps, you may want to defer username generation to a background task. Keep `CLERK_AUTO_GENERATE_USERNAME` disabled (the default) and use the `clerk_user_created` signal to trigger your async task:

```python
# myapp/signals.py
from django.dispatch import receiver
from django_clerk_users.webhooks.signals import clerk_user_created


@receiver(clerk_user_created)
def handle_user_created(sender, user, clerk_data, **kwargs):
    from myapp.tasks import generate_username_task

    generate_username_task.delay(user.pk)
```

```python
# myapp/tasks.py (Celery example)
from celery import shared_task
from django_clerk_users.utils import generate_username_for_user


@shared_task
def generate_username_task(user_id: int):
    return generate_username_for_user(user_id)
```

### Backfilling Existing Users

To generate usernames for existing users without one:

```python
from django_clerk_users.utils import generate_usernames_for_users_without

# Synchronous backfill
count = generate_usernames_for_users_without()

# With custom prefix
count = generate_usernames_for_users_without(prefix="member")
```

## Password Sync

When you change a user's password in Django, it can automatically sync to Clerk:

```python
# Sync password to both Django and Clerk (default)
user.set_password("new_password")
user.save()

# Django only - skip Clerk sync
user.set_password("new_password", sync_to_clerk=False)
user.save()
```

Notes:
- Sync is enabled by default (`sync_to_clerk=True`)
- Users without a `clerk_id` (e.g., Django admin users) skip Clerk sync automatically
- Clerk API errors are logged but don't prevent the Django password from being set

Disable global password sync when Django passwords are only for local session
users or staff accounts:

```python
# settings.py
CLERK_SYNC_PASSWORDS = False
```

Existing projects can also use the legacy opt-out flag:

```python
CLERK_DISABLE_PASSWORD_SYNC = True
```

## Configuration Reference

| Setting | Required | Default | Description |
|---------|----------|---------|-------------|
| `CLERK_SECRET_KEY` | Yes | - | Your Clerk secret key |
| `CLERK_WEBHOOK_SIGNING_KEY` | Yes* | - | Webhook signing secret (*required for webhooks) |
| `CLERK_FRONTEND_HOSTS` | Yes | `[]` | Authorized frontend URLs |
| `CLERK_AUTH_PARTIES` | No | `[]` | Alias for `CLERK_FRONTEND_HOSTS` |
| `CLERK_JWT_KEY` | No | - | PEM public key for networkless token verification (skips the JWKS request) |
| `CLERK_CLIENT_BACKEND` | No | `"thin"` | Clerk API client: `"thin"` (built-in) or `"sdk"` (requires the `[sdk]` extra) |
| `CLERK_SESSION_REVALIDATION_SECONDS` | No | `300` | JWT revalidation interval (seconds) |
| `CLERK_CACHE_TIMEOUT` | No | `300` | User cache timeout (seconds) |
| `CLERK_ORG_CACHE_TIMEOUT` | No | `900` | Organization cache timeout (seconds) |
| `CLERK_API_TIMEOUT_MS` | No | `10000` | Timeout for server-side Clerk SDK helper calls |
| `CLERK_WEBHOOK_DEDUP_TIMEOUT` | No | `45` | Webhook deduplication cache timeout (seconds) |
| `CLERK_AUTO_GENERATE_USERNAME` | No | `False` | Auto-generate usernames synchronously |
| `CLERK_AUTO_GENERATE_USERNAME_PREFIX` | No | `"user"` | Prefix for auto-generated usernames |
| `CLERK_SYNC_PASSWORDS` | No | `True` | Sync Django password changes to Clerk when a user has `clerk_id` |
| `CLERK_DISABLE_PASSWORD_SYNC` | No | `False` | Legacy opt-out; disables password sync when `True` |

Comma-separated strings are accepted for `CLERK_FRONTEND_HOSTS` and
`CLERK_AUTH_PARTIES`. Numeric settings may be provided as strings. Boolean
settings accept common environment values such as `true`, `false`, `1`, and `0`.

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or PR on [GitHub](https://github.com/jmitchel3/django-clerk-users).
