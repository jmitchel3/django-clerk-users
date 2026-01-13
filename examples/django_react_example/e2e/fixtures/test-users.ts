/**
 * Pre-defined test users for E2E testing with Clerk.
 *
 * These users should be created in your Clerk development instance
 * before running E2E tests. Use test email patterns for OTP bypass.
 *
 * Test Email Pattern: user+clerk_test@example.com
 * - Won't send actual emails in test mode
 * - Use OTP code: 424242
 *
 * Test Phone Pattern: +1 (XXX) 555-0100 through +1 (XXX) 555-0199
 * - Won't send actual SMS in test mode
 * - Use OTP code: 424242
 *
 * @see https://clerk.com/docs/testing/test-emails-and-phones
 */

export interface TestUser {
  /** Email address (use +clerk_test suffix for test mode) */
  email: string;
  /** Password for the test user */
  password: string;
  /** First name */
  firstName: string;
  /** Last name */
  lastName: string;
  /** Description of this test user's role */
  description: string;
}

/**
 * Standard test user for basic authentication flows.
 *
 * Setup in Clerk Dashboard:
 * 1. Go to your development instance
 * 2. Users > Create user
 * 3. Use these credentials
 */
export const TEST_USER: TestUser = {
  email: "testuser+clerk_test@example.com",
  password: "TestPassword123!",
  firstName: "Test",
  lastName: "User",
  description: "Standard test user for basic auth flows",
};

/**
 * Admin test user for testing elevated permissions.
 */
export const ADMIN_USER: TestUser = {
  email: "admin+clerk_test@example.com",
  password: "AdminPassword123!",
  firstName: "Admin",
  lastName: "User",
  description: "Admin user for testing elevated permissions",
};

/**
 * Secondary test user for multi-user scenarios.
 */
export const SECONDARY_USER: TestUser = {
  email: "secondary+clerk_test@example.com",
  password: "SecondaryPassword123!",
  firstName: "Secondary",
  lastName: "Tester",
  description: "Secondary user for multi-user test scenarios",
};

/**
 * All available test users.
 */
export const ALL_TEST_USERS: TestUser[] = [TEST_USER, ADMIN_USER, SECONDARY_USER];

/**
 * OTP code used for test emails/phones in Clerk test mode.
 */
export const TEST_OTP_CODE = "424242";

/**
 * Generate a unique test email for one-off test scenarios.
 * Uses the +clerk_test suffix so emails aren't actually sent.
 */
export function generateTestEmail(base: string = "e2e"): string {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  return `${base}+clerk_test_${timestamp}_${random}@example.com`;
}

/**
 * Generate a test phone number in Clerk's reserved range.
 * Format: +1XXX5550100 through +1XXX5550199
 */
export function generateTestPhone(areaCode: string = "201", suffix: number = 0): string {
  const clampedSuffix = Math.max(0, Math.min(99, suffix));
  return `+1${areaCode}55501${clampedSuffix.toString().padStart(2, "0")}`;
}
