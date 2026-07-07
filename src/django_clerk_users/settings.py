"""
Settings for django-clerk-users package.

All settings are prefixed with CLERK_ and can be set in Django's settings.py.
"""

from django.conf import settings

# Required settings
CLERK_SECRET_KEY: str | None = getattr(settings, "CLERK_SECRET_KEY", None)
CLERK_WEBHOOK_SIGNING_KEY: str | None = getattr(
    settings, "CLERK_WEBHOOK_SIGNING_KEY", None
)

# Authorized frontend hosts for JWT validation (authorized_parties)
CLERK_FRONTEND_HOSTS: list[str] = getattr(settings, "CLERK_FRONTEND_HOSTS", [])

# Alias for CLERK_FRONTEND_HOSTS for consistency with existing implementations
CLERK_AUTH_PARTIES: list[str] = getattr(
    settings, "CLERK_AUTH_PARTIES", CLERK_FRONTEND_HOSTS
)

# Session revalidation interval in seconds (default: 5 minutes)
CLERK_SESSION_REVALIDATION_SECONDS: int = getattr(
    settings, "CLERK_SESSION_REVALIDATION_SECONDS", 300
)

# Cache timeout for JWT payloads and user lookups (default: 5 minutes)
CLERK_CACHE_TIMEOUT: int = getattr(settings, "CLERK_CACHE_TIMEOUT", 300)

# Cache timeout for organization lookups (default: 15 minutes)
CLERK_ORG_CACHE_TIMEOUT: int = getattr(settings, "CLERK_ORG_CACHE_TIMEOUT", 900)

# Default timeout for server-side Clerk SDK helper calls (milliseconds)
CLERK_API_TIMEOUT_MS: int = getattr(settings, "CLERK_API_TIMEOUT_MS", 10_000)

# Webhook deduplication cache timeout (default: 45 seconds)
CLERK_WEBHOOK_DEDUP_TIMEOUT: int = getattr(settings, "CLERK_WEBHOOK_DEDUP_TIMEOUT", 45)

# Auto-generate usernames for users without one (default: False)
# When enabled, users created/updated without a username will get one auto-generated
CLERK_AUTO_GENERATE_USERNAME: bool = getattr(
    settings, "CLERK_AUTO_GENERATE_USERNAME", False
)

# Prefix for auto-generated usernames (default: "user")
# Usernames will be generated as: {prefix}_{uuid8} (e.g., "user_abc12345")
CLERK_AUTO_GENERATE_USERNAME_PREFIX: str = getattr(
    settings, "CLERK_AUTO_GENERATE_USERNAME_PREFIX", "user"
)

# Password sync is enabled by default for backwards compatibility.
# CLERK_DISABLE_PASSWORD_SYNC is retained for apps that already use that flag.
CLERK_DISABLE_PASSWORD_SYNC: bool = getattr(
    settings, "CLERK_DISABLE_PASSWORD_SYNC", False
)
CLERK_SYNC_PASSWORDS: bool = getattr(
    settings, "CLERK_SYNC_PASSWORDS", not CLERK_DISABLE_PASSWORD_SYNC
)
