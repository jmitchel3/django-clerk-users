"""
Settings for django-clerk-users package.

All settings are prefixed with CLERK_ and can be set in Django's settings.py.
"""

from django.conf import settings


TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, list | tuple | set):
        raw_values = value
    else:
        return []

    values = []
    for item in raw_values:
        if item is None:
            continue
        if isinstance(item, bytes):
            try:
                item = item.decode("utf-8")
            except UnicodeDecodeError:
                continue
        item = str(item).strip()
        if item:
            values.append(item)
    return values


def _int_setting(setting_name: str, default: int, *, minimum: int | None = None) -> int:
    raw_value = getattr(settings, setting_name, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        if not normalized:
            return default
        return default
    if isinstance(value, int):
        return bool(value)
    return default


def _bool_setting(setting_name: str, default: bool) -> bool:
    return _coerce_bool(getattr(settings, setting_name, default), default)


# Required settings
CLERK_SECRET_KEY: str | None = getattr(settings, "CLERK_SECRET_KEY", None)
CLERK_WEBHOOK_SIGNING_KEY: str | None = getattr(
    settings, "CLERK_WEBHOOK_SIGNING_KEY", None
)

# Authorized frontend hosts for JWT validation (authorized_parties)
CLERK_FRONTEND_HOSTS: list[str] = _string_list(
    getattr(settings, "CLERK_FRONTEND_HOSTS", [])
)

# Alias for CLERK_FRONTEND_HOSTS for consistency with existing implementations
CLERK_AUTH_PARTIES: list[str] = _string_list(
    getattr(settings, "CLERK_AUTH_PARTIES", CLERK_FRONTEND_HOSTS)
)

# Session revalidation interval in seconds (default: 5 minutes)
CLERK_SESSION_REVALIDATION_SECONDS: int = _int_setting(
    "CLERK_SESSION_REVALIDATION_SECONDS", 300, minimum=0
)

# Cache timeout for JWT payloads and user lookups (default: 5 minutes)
CLERK_CACHE_TIMEOUT: int = _int_setting("CLERK_CACHE_TIMEOUT", 300)

# Cache timeout for organization lookups (default: 15 minutes)
CLERK_ORG_CACHE_TIMEOUT: int = _int_setting("CLERK_ORG_CACHE_TIMEOUT", 900)

# Default timeout for server-side Clerk SDK helper calls (milliseconds)
CLERK_API_TIMEOUT_MS: int = _int_setting("CLERK_API_TIMEOUT_MS", 10_000, minimum=1)

# Webhook deduplication cache timeout (default: 45 seconds)
CLERK_WEBHOOK_DEDUP_TIMEOUT: int = _int_setting(
    "CLERK_WEBHOOK_DEDUP_TIMEOUT", 45, minimum=1
)

# Auto-generate usernames for users without one (default: False)
# When enabled, users created/updated without a username will get one auto-generated
CLERK_AUTO_GENERATE_USERNAME: bool = _bool_setting(
    "CLERK_AUTO_GENERATE_USERNAME", False
)

# Prefix for auto-generated usernames (default: "user")
# Usernames will be generated as: {prefix}_{uuid8} (e.g., "user_abc12345")
CLERK_AUTO_GENERATE_USERNAME_PREFIX: str = getattr(
    settings, "CLERK_AUTO_GENERATE_USERNAME_PREFIX", "user"
)

# Password sync is enabled by default for backwards compatibility.
# CLERK_DISABLE_PASSWORD_SYNC is retained for apps that already use that flag.
CLERK_DISABLE_PASSWORD_SYNC: bool = _bool_setting("CLERK_DISABLE_PASSWORD_SYNC", False)
CLERK_SYNC_PASSWORDS: bool = _bool_setting(
    "CLERK_SYNC_PASSWORDS", not CLERK_DISABLE_PASSWORD_SYNC
)
