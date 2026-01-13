# Django Clerk Users

Integrate [Clerk](https://clerk.com) authentication with Django.

> **Note:** This package is in early development (v0.0.2). APIs may change.

## Features

- Custom user model (`ClerkUser`) with Clerk integration
- JWT token validation via Clerk SDK
- Session-based authentication middleware (validates once, caches in session)
- Webhook handling with Svix signature verification
- Optional organizations support (separate sub-app)
- Django REST Framework authentication (optional)

## Installation

```bash
pip install django-clerk-users
```

For Django REST Framework support:

```bash
pip install django-clerk-users[drf]
```

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
```

## Configuration Reference

| Setting | Required | Default | Description |
|---------|----------|---------|-------------|
| `CLERK_SECRET_KEY` | Yes | - | Your Clerk secret key |
| `CLERK_WEBHOOK_SIGNING_KEY` | Yes* | - | Webhook signing secret (*required for webhooks) |
| `CLERK_FRONTEND_HOSTS` | Yes | `[]` | Authorized frontend URLs |
| `CLERK_AUTH_PARTIES` | No | `[]` | Alias for `CLERK_FRONTEND_HOSTS` |
| `CLERK_SESSION_REVALIDATION_SECONDS` | No | `300` | JWT revalidation interval (seconds) |
| `CLERK_CACHE_TIMEOUT` | No | `300` | User cache timeout (seconds) |
| `CLERK_ORG_CACHE_TIMEOUT` | No | `900` | Organization cache timeout (seconds) |
| `CLERK_WEBHOOK_DEDUP_TIMEOUT` | No | `45` | Webhook deduplication cache timeout (seconds) |

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or PR on [GitHub](https://github.com/jmitchel3/django-clerk-users).
