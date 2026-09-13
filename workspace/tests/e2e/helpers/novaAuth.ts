import type { Page } from "@playwright/test";

/**
 * Synthetic §63 demo credentials from make reset-demo / seed_formkok_demo.
 * Matches NovaLoginGate defaults in WebsiteProspectAgent — never Formkök PII.
 */
export const DEMO_NOVA_OPERATOR = {
  email: "tenant-wide@example.invalid",
  password: "salesos",
} as const;

const TOKEN_KEY = "salesos.salesDeskToken";
const API_BASE_KEY = "salesos.salesDeskApiBase";

/**
 * Wipe Sales Desk / Nova session keys before the app hydrates so each smoke
 * starts at the Nova login gate.
 */
export async function clearNovaSession(page: Page): Promise<void> {
  await page.addInitScript(
    ({ tokenKey, apiBaseKey }) => {
      try {
        window.localStorage.removeItem(tokenKey);
        window.localStorage.removeItem(apiBaseKey);
      } catch {
        /* ignore — private mode / blocked storage */
      }
    },
    { tokenKey: TOKEN_KEY, apiBaseKey: API_BASE_KEY },
  );
}

/**
 * Open /nova unsigned. Nova lives in internal-pilot-ui (:5173 direct Vite,
 * or /nova via unified host). Prefer SALESOS_E2E_NOVA_URL / project baseURL.
 */
export async function openSignedOutNova(page: Page): Promise<void> {
  const response = await page.goto("/nova");
  if (response == null || (!response.ok() && response.status() !== 304)) {
    throw new Error(
      "Nova host must serve /nova (internal-pilot-ui :5173 or unified host).",
    );
  }

  const loginHeading = page.getByRole("heading", {
    name: "Logga in för att fortsätta",
  });
  try {
    await loginHeading.waitFor({ timeout: 5_000 });
    return;
  } catch {
    // Previous local run may have left a valid synthetic session.
  }

  const logout = page.getByRole("button", { name: /Logga ut|Logout/i });
  if (await logout.isVisible().catch(() => false)) {
    await logout.click();
  }
  await loginHeading.waitFor({ timeout: 20_000 });
}

/**
 * Sign in via NovaLoginGate (OAuth2 form username+password → Bearer token in
 * salesos.salesDeskToken). Requires demo API on the Vite /api proxy (:8001).
 */
export async function loginNova(
  page: Page,
  credentials: { email: string; password: string } = DEMO_NOVA_OPERATOR,
): Promise<void> {
  await openSignedOutNova(page);

  await page.getByLabel("E-post").fill(credentials.email);
  await page.getByLabel("Lösenord").fill(credentials.password);
  await page.getByRole("button", { name: "Logga in", exact: true }).click();

  // Empty or populated live workspace both prove auth + summary/prospects loaded.
  await page
    .getByRole("heading", { name: /Webbprospektering|Nova/ })
    .first()
    .waitFor({ timeout: 20_000 });
  await page.getByText("NOVA · LIVE").or(page.getByText("NOVA")).first().waitFor({
    timeout: 20_000,
  });
}
