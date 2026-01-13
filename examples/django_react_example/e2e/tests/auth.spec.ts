import { test, expect } from "@playwright/test";
import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { TEST_USER, TEST_OTP_CODE } from "../fixtures/test-users";

/**
 * Authentication flow tests using Clerk.
 *
 * Prerequisites:
 * 1. Create the TEST_USER in your Clerk development instance
 * 2. Set CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY env vars
 * 3. Ensure test mode is enabled (default for development instances)
 */

test.describe("Authentication", () => {
  test.beforeEach(async ({ page }) => {
    // Set up the Clerk testing token to bypass bot detection
    await setupClerkTestingToken({ page });
  });

  test("should show sign in button when not authenticated", async ({ page }) => {
    await page.goto("/");

    // Look for Clerk's sign-in button
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("should sign in with email and password", async ({ page }) => {
    await page.goto("/");

    // Click sign in button
    await page.getByRole("button", { name: /sign in/i }).click();

    // Fill in credentials
    await page.getByLabel(/email/i).fill(TEST_USER.email);
    await page.getByRole("button", { name: /continue/i }).click();

    // Enter password
    await page.getByLabel(/password/i).fill(TEST_USER.password);
    await page.getByRole("button", { name: /continue/i }).click();

    // Should be signed in - look for user button or profile indicator
    await expect(page.getByRole("button", { name: /user/i })).toBeVisible({
      timeout: 10000,
    });
  });

  test("should sign in with OTP (test mode)", async ({ page }) => {
    await page.goto("/");

    // Click sign in
    await page.getByRole("button", { name: /sign in/i }).click();

    // Use email with +clerk_test suffix
    await page.getByLabel(/email/i).fill(TEST_USER.email);
    await page.getByRole("button", { name: /continue/i }).click();

    // If OTP option is available, use the test OTP code
    const otpInput = page.locator('input[name="code"]').first();
    if (await otpInput.isVisible()) {
      await otpInput.fill(TEST_OTP_CODE);
    }
  });

  test("should sign out", async ({ page }) => {
    // First sign in
    await page.goto("/");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.getByLabel(/email/i).fill(TEST_USER.email);
    await page.getByRole("button", { name: /continue/i }).click();
    await page.getByLabel(/password/i).fill(TEST_USER.password);
    await page.getByRole("button", { name: /continue/i }).click();

    // Wait for sign in to complete
    await expect(page.getByRole("button", { name: /user/i })).toBeVisible({
      timeout: 10000,
    });

    // Click user button and sign out
    await page.getByRole("button", { name: /user/i }).click();
    await page.getByRole("menuitem", { name: /sign out/i }).click();

    // Should see sign in button again
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible({
      timeout: 10000,
    });
  });
});
