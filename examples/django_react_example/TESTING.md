# Testing with Clerk

This guide explains how to set up and run tests for applications using django-clerk-users with Clerk authentication.

## Overview

Clerk provides several testing approaches:

1. **Test Mode** - Use special email/phone patterns that bypass actual delivery
2. **Backend API** - Create test users programmatically
3. **Testing Tokens** - Bypass bot detection for E2E tests
4. **Playwright/Cypress Integration** - First-class support for E2E testing

## Test Email and Phone Patterns

In Clerk's test mode (enabled by default for development instances):

### Test Emails
- Pattern: `anyuser+clerk_test@example.com`
- These emails won't trigger actual email delivery
- Use OTP code: `424242`

```python
# Example test emails
"testuser+clerk_test@example.com"
"admin+clerk_test@example.com"
"e2e+clerk_test_12345@example.com"
```

### Test Phone Numbers
- Pattern: `+1 (XXX) 555-0100` through `+1 (XXX) 555-0199`
- These numbers won't trigger actual SMS delivery
- Use OTP code: `424242`

```python
# Example test phones
"+12015550100"
"+14155550142"
"+18005550199"
```

## Python Testing Utilities

django-clerk-users provides testing utilities for Django tests:

### Quick Start

```python
from django.test import TestCase
from django_clerk_users.testing import (
    ClerkTestClient,
    ClerkTestMixin,
    make_test_email,
    make_test_phone,
    TEST_OTP_CODE,
)

# Option 1: Use ClerkTestMixin for automatic setup/teardown
class MyTestCase(ClerkTestMixin, TestCase):
    def test_protected_endpoint(self):
        response = self.client.get(
            "/api/protected/",
            **self.get_auth_header()  # Uses self.test_user
        )
        self.assertEqual(response.status_code, 200)

# Option 2: Manual control with ClerkTestClient
class ManualTestCase(TestCase):
    def setUp(self):
        self.clerk = ClerkTestClient()
        self.user = self.clerk.create_test_user()

    def tearDown(self):
        self.clerk.delete_user(self.user.id)

    def test_something(self):
        token = self.clerk.get_session_token(self.user.id)
        # Use token in requests...
```

### Available Functions

```python
from django_clerk_users.testing import (
    # Client for creating test users via Clerk API
    ClerkTestClient,

    # Mixin for Django TestCase with automatic user setup
    ClerkTestMixin,

    # Data class for test user info
    TestUserData,

    # Generate test email addresses
    make_test_email,      # -> "testuser+clerk_test_abc123@example.com"

    # Generate test phone numbers
    make_test_phone,      # -> "+12015550100"

    # OTP code for test mode
    TEST_OTP_CODE,        # "424242"
)
```

### ClerkTestClient Methods

```python
client = ClerkTestClient()

# Create a test user
user = client.create_test_user(
    email="test+clerk_test@example.com",  # Optional, auto-generated if not provided
    first_name="Test",
    last_name="User",
    password="optional_password",
)

# Create a session and get token
token = client.get_session_token(user.id)

# Use in requests
response = requests.get(
    "http://localhost:8000/api/protected/",
    headers={"Authorization": f"Bearer {token}"}
)

# Clean up
client.delete_user(user.id)
```

## E2E Testing with Playwright

### Setup

1. Install dependencies:
   ```bash
   cd e2e
   npm install
   ```

2. Set environment variables:
   ```bash
   export CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
   export CLERK_SECRET_KEY=sk_test_xxxxx
   ```

3. Create test users in Clerk:
   ```bash
   npm run setup:users
   ```

### Running Tests

```bash
# Run all tests
npm test

# Run with UI
npm run test:ui

# Run in headed mode (see browser)
npm run test:headed

# Debug mode
npm run test:debug
```

### Pre-defined Test Users

Test users are defined in `e2e/fixtures/test-users.ts`:

| User | Email | Password | Description |
|------|-------|----------|-------------|
| TEST_USER | testuser+clerk_test@example.com | TestPassword123! | Standard test user |
| ADMIN_USER | admin+clerk_test@example.com | AdminPassword123! | Admin user |
| SECONDARY_USER | secondary+clerk_test@example.com | SecondaryPassword123! | Multi-user scenarios |

### Example Test

```typescript
import { test, expect } from "@playwright/test";
import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { TEST_USER } from "../fixtures/test-users";

test("should access protected page", async ({ page }) => {
  // Bypass Clerk bot detection
  await setupClerkTestingToken({ page });

  // Sign in
  await page.goto("/");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.getByLabel(/email/i).fill(TEST_USER.email);
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByLabel(/password/i).fill(TEST_USER.password);
  await page.getByRole("button", { name: /continue/i }).click();

  // Verify authenticated
  await expect(page.getByRole("button", { name: /user/i })).toBeVisible();
});
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Playwright
        run: |
          cd e2e
          npm ci
          npx playwright install --with-deps

      - name: Run E2E tests
        env:
          CLERK_PUBLISHABLE_KEY: ${{ secrets.CLERK_PUBLISHABLE_KEY }}
          CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}
        run: |
          cd e2e
          npm test
```

### Important Security Notes

1. **Never commit secrets** - Use environment variables or CI secrets
2. **Use development instances** - Test mode only works on development instances
3. **Clean up test users** - Delete test users after test runs to avoid clutter
4. **Protect API keys** - Especially `CLERK_SECRET_KEY` in CI environments

## Session Token Notes

- Clerk session tokens expire after **60 seconds**
- For longer tests, refresh the token before each request
- The `ClerkTestMixin` handles this automatically for Django tests

## Troubleshooting

### "Bot traffic detected" Error
- Ensure you're calling `setupClerkTestingToken({ page })` in Playwright tests
- Verify `CLERK_SECRET_KEY` is set correctly

### Test Emails Being Sent
- Make sure email includes `+clerk_test` suffix
- Verify your instance is in development mode

### 401 Errors in Tests
- Check that the session token hasn't expired (60s lifetime)
- Verify `CLERK_SECRET_KEY` matches your development instance
- Ensure the user exists in Clerk

## References

- [Clerk Testing Overview](https://clerk.com/docs/testing/overview)
- [Test Emails and Phones](https://clerk.com/docs/testing/test-emails-and-phones)
- [Playwright Integration](https://clerk.com/docs/testing/playwright)
- [Testing Tokens](https://clerk.com/docs/testing/testing-tokens)
