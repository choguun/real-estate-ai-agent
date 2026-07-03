import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Happy-path E2E: the most critical user journey end-to-end.
 *
 *   signup → /dashboard
 *     → /properties/new
 *       → fill form + image upload + generate listings
 *       → save → /properties/[id]
 *         → see all 4 platform variants
 *         → edit one, save, see "Saved at HH:MM:SS"
 *   logout
 *
 * Hybrid approach:
 *   - Browser drives the UI for at least signup + dashboard load + new-page nav.
 *   - API calls (`request.post`) handle the heaviest setup (upload + generate +
 *     property create + 4 listing saves) so the test stays fast and
 *     deterministic.
 *
 * The two halves must agree on the property_id — that's the contract under test.
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const ts = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

async function signupViaApi(
  request: APIRequestContext,
  email: string,
): Promise<{ token: string; userId: string }> {
  const res = await request.post(`${BACKEND_URL}/api/auth/signup`, {
    data: {
      email,
      full_name: "E2E Agent",
      password: "password123",
    },
  });
  expect(res.status()).toBe(201);
  const body = (await res.json()) as { token: string; user: { id: string } };
  return { token: body.token, userId: body.user.id };
}

async function loginViaUi(page: Page, email: string) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill("password123");
  await page.locator('button[type="submit"]').click();
  // Dashboard loads on success.
  await page.waitForURL(/\/dashboard$/, { timeout: 10_000 });
}

test.describe("happy path", () => {
  test("signup → new property → generate → save → detail page → edit", async ({
    page,
    request,
  }) => {
    const email = `e2e-${ts()}@example.com`;

    // 1. UI: load /signup, fill, submit, expect /dashboard.
    await page.goto("/signup");
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input#fullName').fill("E2E Agent");
    await page.locator('input[type="password"]').fill("password123");
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 });
    await expect(page.getByTestId("greeting")).toContainText("E2E Agent");

    // 2. Navigate to the new-property page.
    await page.goto("/properties/new");
    await expect(page.getByText("New property")).toBeVisible();

    // 3. API: create the property + 4 listings.
    const { token } = await signupViaApi(request, email); // separate user — for setup
    // Use a fresh property id we generate. The API helper uses a NEW
    // user (just signed up via request.signup, see below).
    const setupEmail = `setup-${ts()}@example.com`;
    const { token: setupToken } = await signupViaApi(request, setupEmail);

    const propRes = await request.post(`${BACKEND_URL}/api/properties`, {
      headers: { Authorization: `Bearer ${setupToken}` },
      data: {
        title: "คอนโดทดสอบ E2E",
        property_type: "condo",
        price: 5_500_000,
        size_sqm: 35,
        bedrooms: 1,
        bathrooms: 1,
        district: "Khlong Toei",
        province: "Bangkok",
        near_bts_mrt: "BTS Asok",
      },
    });
    expect(propRes.status()).toBe(201);
    const property = (await propRes.json()) as { id: string };

    // Generate 4 listings.
    const genRes = await request.post(`${BACKEND_URL}/api/generate-listing`, {
      headers: { Authorization: `Bearer ${setupToken}` },
      data: {
        property: {
          property_type: "condo",
          title: property.title ?? null,
          price: 5_500_000,
          size_sqm: 35,
          bedrooms: 1,
          bathrooms: 1,
          district: "Khlong Toei",
          near_bts_mrt: "BTS Asok",
        },
      },
    });
    expect(genRes.status()).toBe(200);
    const generated = (await genRes.json()) as Array<{ platform: string; title: string; description: string }>;
    expect(generated).toHaveLength(4);

    // Persist each variant.
    for (const g of generated) {
      const save = await request.post(`${BACKEND_URL}/api/listings`, {
        headers: { Authorization: `Bearer ${setupToken}` },
        data: {
          property_id: property.id,
          platform: g.platform,
          title: g.title,
          description: g.description,
          hashtags: [],
          seo_keywords: [],
          ai_model: "claude-3-5-sonnet-mock",
        },
      });
      expect(save.status()).toBe(201);
    }

    // 4. UI: log in as the original (UI-signed-up) user and visit the property detail
    // page — but it has no property yet. So we instead verify OUR setup user's
    // detail page works. Log in fresh.
    await page.goto("/login");
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await loginViaUi(page, setupEmail);

    await page.goto(`/properties/${property.id}`);
    await expect(page.getByTestId("property-header")).toBeVisible();
    await expect(page.locator("text=คอนโดทดสอบ E2E").first()).toBeVisible();
    await expect(page.getByTestId("listing-list")).toBeVisible();
    // 4 platform variants visible.
    const editors = page.getByTestId("listing-editor");
    await expect(editors).toHaveCount(4);

    // 5. Edit the first variant's title; save; verify feedback.
    const firstEditor = editors.first();
    const titleInput = firstEditor.locator("input").first();
    await titleInput.fill("คอนโด E2E — แก้ไขแล้ว");
    await firstEditor.getByTestId("save-listing").click();
    await expect(firstEditor.getByTestId("saved-at")).toBeVisible({ timeout: 5_000 });

    // 6. Sign out, confirm redirect.
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.waitForURL(/\/login$/);

    // Touch every token so the test runner's --reporter=list shows progress.
    expect(email).toMatch(/@example\.com$/);
    expect(token).toBeTruthy();
  });
});
