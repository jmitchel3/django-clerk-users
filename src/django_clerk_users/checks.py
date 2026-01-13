"""
Django system checks for django-clerk-users configuration.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def check_clerk_secret_key(app_configs, **kwargs):
    """Check that CLERK_SECRET_KEY is configured."""
    errors = []
    if not getattr(settings, "CLERK_SECRET_KEY", None):
        errors.append(
            Error(
                "CLERK_SECRET_KEY is not configured.",
                hint="Set CLERK_SECRET_KEY in your Django settings.",
                id="django_clerk_users.E001",
            )
        )
    return errors


@register()
def check_clerk_webhook_signing_key(app_configs, **kwargs):
    """Check that CLERK_WEBHOOK_SIGNING_KEY is configured."""
    warnings = []
    if not getattr(settings, "CLERK_WEBHOOK_SIGNING_KEY", None):
        warnings.append(
            Warning(
                "CLERK_WEBHOOK_SIGNING_KEY is not configured.",
                hint=(
                    "Set CLERK_WEBHOOK_SIGNING_KEY in your Django settings "
                    "if you plan to use Clerk webhooks."
                ),
                id="django_clerk_users.W001",
            )
        )
    return warnings


@register()
def check_auth_user_model(app_configs, **kwargs):
    """Check that AUTH_USER_MODEL is configured for Clerk."""
    warnings = []
    auth_user_model = getattr(settings, "AUTH_USER_MODEL", "auth.User")

    # Check if using a Clerk-compatible user model
    if not (
        auth_user_model.startswith("django_clerk_users.")
        or "clerk" in auth_user_model.lower()
    ):
        warnings.append(
            Warning(
                f"AUTH_USER_MODEL is set to '{auth_user_model}'.",
                hint=(
                    "Consider using 'django_clerk_users.ClerkUser' or a custom model "
                    "that extends AbstractClerkUser for full Clerk integration."
                ),
                id="django_clerk_users.W002",
            )
        )
    return warnings


@register()
def check_middleware_installed(app_configs, **kwargs):
    """Check that ClerkAuthMiddleware is installed."""
    warnings = []
    middleware = getattr(settings, "MIDDLEWARE", [])

    clerk_middleware = "django_clerk_users.middleware.ClerkAuthMiddleware"
    if clerk_middleware not in middleware:
        warnings.append(
            Warning(
                "ClerkAuthMiddleware is not in MIDDLEWARE.",
                hint=(
                    f"Add '{clerk_middleware}' to MIDDLEWARE in your Django settings "
                    "for automatic Clerk authentication."
                ),
                id="django_clerk_users.W003",
            )
        )
    return warnings


@register()
def check_authentication_backend(app_configs, **kwargs):
    """Check that ClerkBackend is in AUTHENTICATION_BACKENDS."""
    warnings = []
    backends = getattr(settings, "AUTHENTICATION_BACKENDS", [])

    clerk_backend = "django_clerk_users.authentication.ClerkBackend"
    if clerk_backend not in backends:
        warnings.append(
            Warning(
                "ClerkBackend is not in AUTHENTICATION_BACKENDS.",
                hint=(
                    f"Add '{clerk_backend}' to AUTHENTICATION_BACKENDS in your "
                    "Django settings."
                ),
                id="django_clerk_users.W004",
            )
        )
    return warnings


@register()
def check_frontend_hosts(app_configs, **kwargs):
    """Check that CLERK_FRONTEND_HOSTS is configured."""
    warnings = []
    frontend_hosts = getattr(settings, "CLERK_FRONTEND_HOSTS", [])
    auth_parties = getattr(settings, "CLERK_AUTH_PARTIES", [])

    if not frontend_hosts and not auth_parties:
        warnings.append(
            Warning(
                "CLERK_FRONTEND_HOSTS is not configured.",
                hint=(
                    "Set CLERK_FRONTEND_HOSTS in your Django settings to the list of "
                    "frontend URLs that will be sending authenticated requests "
                    "(e.g., ['https://myapp.com', 'http://localhost:3000'])."
                ),
                id="django_clerk_users.W005",
            )
        )
    return warnings
