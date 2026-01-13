import { clerkSetup } from "@clerk/testing/playwright";
import { FullConfig } from "@playwright/test";

/**
 * Global setup for Playwright tests with Clerk.
 *
 * This runs once before all tests and:
 * 1. Obtains a Testing Token from Clerk
 * 2. Makes it available for all subsequent tests
 *
 * The Testing Token bypasses Clerk's bot detection,
 * allowing automated tests to interact with Clerk components.
 *
 * Required environment variables:
 * - CLERK_PUBLISHABLE_KEY: Your Clerk publishable key
 * - CLERK_SECRET_KEY: Your Clerk secret key (for API calls)
 *
 * @see https://clerk.com/docs/testing/playwright
 */
async function globalSetup(config: FullConfig) {
  // Initialize Clerk testing - obtains a testing token
  await clerkSetup();

  // You can also set up test users here if needed
  // See: createTestUser in fixtures/test-users.ts
}

export default globalSetup;
