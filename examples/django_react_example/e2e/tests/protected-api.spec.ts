import { test, expect } from "@playwright/test";
import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { TEST_USER } from "../fixtures/test-users";

/**
 * Tests for protected Django API endpoints.
 *
 * These tests verify that:
 * 1. Protected endpoints require authentication
 * 2. Authenticated users can access protected data
 * 3. The Clerk JWT is properly validated by Django
 */

test.describe("Protected API Endpoints", () => {
  test.beforeEach(async ({ page }) => {
    await setupClerkTestingToken({ page });
  });

  test("should return 401 for unauthenticated requests", async ({ request }) => {
    const response = await request.get("http://localhost:8000/api/protected/");
    expect(response.status()).toBe(401);
  });

  test("should access protected endpoint when authenticated", async ({ page }) => {
    // Sign in first
    await page.goto("/");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.getByLabel(/email/i).fill(TEST_USER.email);
    await page.getByRole("button", { name: /continue/i }).click();
    await page.getByLabel(/password/i).fill(TEST_USER.password);
    await page.getByRole("button", { name: /continue/i }).click();

    // Wait for authentication
    await expect(page.getByRole("button", { name: /user/i })).toBeVisible({
      timeout: 10000,
    });

    // Now test the protected API through the frontend
    // The frontend should include the Clerk token in API requests
    const response = await page.evaluate(async () => {
      const res = await fetch("http://localhost:8000/api/protected/", {
        credentials: "include",
      });
      return {
        status: res.status,
        data: await res.json(),
      };
    });

    expect(response.status).toBe(200);
    expect(response.data).toHaveProperty("user");
  });

  test("should return user profile when authenticated", async ({ page }) => {
    // Sign in
    await page.goto("/");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.getByLabel(/email/i).fill(TEST_USER.email);
    await page.getByRole("button", { name: /continue/i }).click();
    await page.getByLabel(/password/i).fill(TEST_USER.password);
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByRole("button", { name: /user/i })).toBeVisible({
      timeout: 10000,
    });

    // Test profile endpoint
    const response = await page.evaluate(async () => {
      const res = await fetch("http://localhost:8000/api/profile/", {
        credentials: "include",
      });
      return {
        status: res.status,
        data: await res.json(),
      };
    });

    expect(response.status).toBe(200);
    expect(response.data.profile).toHaveProperty("clerk_id");
    expect(response.data.profile.first_name).toBe(TEST_USER.firstName);
  });
});
