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

```python
AUTHENTICATION_BACKENDS = [
    "django_clerk_users.authentication.ClerkBackend",
]
```

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
| `CLERK_SESSION_REVALIDATION_SECONDS` | No | `300` | JWT revalidation interval |
| `CLERK_CACHE_TIMEOUT` | No | `300` | User cache timeout |
| `CLERK_ORG_CACHE_TIMEOUT` | No | `900` | Organization cache timeout |

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or PR on [GitHub](https://github.com/jmitchel3/django-clerk-users).
