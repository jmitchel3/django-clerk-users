# Hybrid Authentication Feature

## Overview

This feature adds support for hybrid authentication, allowing django-clerk-users to work alongside Django's traditional admin authentication. This is particularly useful when your admin panel is on a different domain than your frontend.

## Changes Made

### 1. Middleware Updates (`src/django_clerk_users/middleware/auth.py`)

- Added `_is_clerk_session()` method to distinguish between Clerk sessions and Django admin sessions
- Updated `process_request()` to respect existing Django admin sessions without interference
- Clerk sessions are identified by the presence of `last_clerk_check` in the session
- Django admin sessions (created by `ModelBackend`) are preserved and not validated against Clerk

### 2. Model Updates (`src/django_clerk_users/models.py`)

- Made `clerk_id` field nullable (`null=True`, `blank=True`)
- Updated help text to clarify that `clerk_id` can be null for Django admin users
- Changed `REQUIRED_FIELDS` from `["clerk_id"]` to `[]` to support admin user creation
- Password field (inherited from `AbstractBaseUser`) is now functional for admin users

### 3. Migration (`src/django_clerk_users/migrations/0002_make_clerk_id_nullable.py`)

- New migration to alter `clerk_id` field to allow NULL values
- Maintains unique constraint while allowing NULL

### 4. Documentation Updates (`README.md`)

- Added "Hybrid Authentication" section explaining the feature
- Updated authentication backend configuration to show both options:
  - Clerk-only: `[ClerkBackend]`
  - Hybrid: `[ModelBackend, ClerkBackend]`
- Added instructions for creating admin users via `createsuperuser`
- Explained session handling differences
- Added use cases for hybrid authentication

### 5. Tests (`tests/test_hybrid_auth.py`)

- New test file for hybrid authentication scenarios
- Tests for Django admin session preservation
- Tests for Clerk session handling
- Tests for middleware behavior with both authentication types

## Configuration

### For Clerk-only authentication (existing behavior):

```python
AUTHENTICATION_BACKENDS = [
    "django_clerk_users.authentication.ClerkBackend",
]
```

### For hybrid authentication (new feature):

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # For Django admin
    "django_clerk_users.authentication.ClerkBackend",  # For Clerk JWT
]
```

## How It Works

1. **Clerk Users**: Authenticated via JWT tokens
   - JWT validated on first request
   - Session created with `last_clerk_check` marker
   - Re-validated every 5 minutes (configurable)
   - Has `clerk_id` field populated

2. **Admin Users**: Authenticated via username/password
   - Traditional Django session (no `last_clerk_check` marker)
   - Created via `createsuperuser` command
   - No `clerk_id` (NULL)
   - Can access Django admin panel

3. **Middleware Behavior**:
   - Checks if user is already authenticated
   - If `last_clerk_check` exists → Clerk session (validate/revalidate)
   - If no `last_clerk_check` → Django admin session (preserve as-is)
   - Never interferes with Django admin sessions

## Use Cases

1. **Cross-domain admin access**: Admin on different domain than frontend
2. **Internal staff access**: Staff use Django admin without Clerk accounts
3. **Gradual migration**: Migrate from Django auth to Clerk incrementally
4. **Mixed user types**: Frontend users via Clerk, internal users via Django

## Breaking Changes

- `clerk_id` is now nullable (requires migration)
- `REQUIRED_FIELDS` changed from `["clerk_id"]` to `[]`

Existing deployments will need to run the migration:

```bash
python manage.py migrate django_clerk_users
```

## Testing

Run the new hybrid authentication tests:

```bash
python -m pytest tests/test_hybrid_auth.py -v
```

## Example: Creating Admin User

```bash
# Create superuser (no Clerk account needed)
python manage.py createsuperuser

# Login to Django admin
# Visit: http://your-domain.com/admin/
# Use the email/password you just created
```

## Example: User Table After Migration

| id | email | clerk_id | is_staff | is_superuser | Created via |
|----|-------|----------|----------|--------------|-------------|
| 1 | admin@example.com | NULL | True | True | createsuperuser |
| 2 | user@example.com | user_2abc123 | False | False | Clerk webhook |
| 3 | staff@example.com | user_2def456 | True | False | Clerk webhook + manual flag |

## Notes

- Django admin users (NULL clerk_id) cannot authenticate via Clerk JWT
- Clerk users (with clerk_id) can authenticate via either method if they have a password set
- The middleware automatically detects which auth method was used
- No changes needed to existing Clerk-only deployments (backward compatible)
