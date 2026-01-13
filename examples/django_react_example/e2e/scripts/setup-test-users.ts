#!/usr/bin/env tsx
/**
 * Script to set up test users in Clerk for E2E testing.
 *
 * This script creates the predefined test users in your Clerk development
 * instance using the Backend API. Run this once to set up your test users.
 *
 * Usage:
 *   # Set your Clerk secret key
 *   export CLERK_SECRET_KEY=sk_test_xxxxx
 *
 *   # Run the script
 *   npm run setup:users
 *
 * Or with npx:
 *   CLERK_SECRET_KEY=sk_test_xxxxx npx tsx scripts/setup-test-users.ts
 */

import { ALL_TEST_USERS, type TestUser } from "../fixtures/test-users";

const CLERK_SECRET_KEY = process.env.CLERK_SECRET_KEY;

if (!CLERK_SECRET_KEY) {
  console.error("Error: CLERK_SECRET_KEY environment variable is required");
  console.error("Export it before running: export CLERK_SECRET_KEY=sk_test_xxxxx");
  process.exit(1);
}

const CLERK_API_URL = "https://api.clerk.com/v1";

interface ClerkUser {
  id: string;
  email_addresses: { email_address: string }[];
  first_name: string;
  last_name: string;
}

async function clerkRequest<T>(
  method: string,
  endpoint: string,
  body?: unknown
): Promise<T> {
  const response = await fetch(`${CLERK_API_URL}${endpoint}`, {
    method,
    headers: {
      Authorization: `Bearer ${CLERK_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Clerk API error (${response.status}): ${error}`);
  }

  return response.json();
}

async function findUserByEmail(email: string): Promise<ClerkUser | null> {
  try {
    const users = await clerkRequest<ClerkUser[]>(
      "GET",
      `/users?email_address=${encodeURIComponent(email)}`
    );
    return users.length > 0 ? users[0] : null;
  } catch {
    return null;
  }
}

async function createUser(testUser: TestUser): Promise<ClerkUser> {
  return clerkRequest<ClerkUser>("POST", "/users", {
    email_address: [testUser.email],
    password: testUser.password,
    first_name: testUser.firstName,
    last_name: testUser.lastName,
    skip_password_checks: true,
    skip_password_requirement: false,
  });
}

async function setupTestUsers() {
  console.log("Setting up test users in Clerk...\n");

  for (const testUser of ALL_TEST_USERS) {
    console.log(`Processing: ${testUser.email}`);
    console.log(`  Description: ${testUser.description}`);

    try {
      // Check if user already exists
      const existingUser = await findUserByEmail(testUser.email);

      if (existingUser) {
        console.log(`  Status: Already exists (ID: ${existingUser.id})`);
      } else {
        // Create the user
        const newUser = await createUser(testUser);
        console.log(`  Status: Created (ID: ${newUser.id})`);
      }
    } catch (error) {
      console.error(`  Status: Error - ${error}`);
    }

    console.log("");
  }

  console.log("Done! Test users are ready for E2E testing.");
  console.log("\nTo run tests:");
  console.log("  cd e2e && npm test");
}

setupTestUsers().catch(console.error);
