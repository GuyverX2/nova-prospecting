import { expect, test } from "@playwright/test";
import {
  clearNovaSession,
  DEMO_NOVA_OPERATOR,
  loginNova,
  openSignedOutNova,
} from "./helpers/novaAuth";
import { installNovaProspectingMocks } from "./helpers/novaProspectingMock";

/**
 * FE-E2E-NOVA-N1-7-001 — Nova prospecting smoke (N1-7).
 *
 * Flow: login → empty surface → manual URL (fixture HTML via mock) →
 * proposal preview → approve disabled without review checks.
 *
 * Preconditions:
 *   make reset-demo
 *   internal-pilot-ui on :5173 + API :8001
 *     (make run-unified-host starts these; or `npm --prefix apps/internal-pilot-ui run dev`)
 *
 * Discovery: Playwright project `nova` (`nova-*.spec.ts`).
 * List without a browser: `npx playwright test --project=nova --list`
 *
 * STOP: no Places scrape · no prod host · no commercially_priceable ·
 * no outbound / deliver / approve clicks · synthetic @example.invalid only.
 */
test.describe("nova prospecting smoke", () => {
  test.beforeEach(async ({ page }) => {
    await clearNovaSession(page);
  });

  test("unsigned /nova renders the Nova login gate", async ({ page }) => {
    await openSignedOutNova(page);

    await expect(
      page.getByRole("heading", { name: "Logga in för att fortsätta" }),
    ).toBeVisible();
    await expect(page.getByLabel("E-post")).toBeVisible();
    await expect(page.getByLabel("Lösenord")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Logga in", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Webbprospektering").first()).toBeVisible();
  });

  test("login → empty → manual URL mock → proposal → approve gated", async ({
    page,
  }) => {
    await installNovaProspectingMocks(page);
    await loginNova(page, DEMO_NOVA_OPERATOR);

    // Empty live workspace (mocked zero prospects; fetch flagged on for analyze path).
    await expect(page.getByText("NOVA · LIVE")).toBeVisible();
    await expect(page.getByText("API ansluten · arbetsytan är tom")).toBeVisible();
    await expect(page.getByLabel("Tom Nova-arbetsyta")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Analysera URL" }).first(),
    ).toBeVisible();

    // Manual URL intake — synthetic company + example.invalid only.
    await page.getByRole("button", { name: "Analysera URL" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Lägg till och analysera en webbplats" }),
    ).toBeVisible();

    await page.getByLabel("Företagsnamn").fill("Exempel Bygg AB");
    await page.getByLabel("Publik webbplats").fill("https://example.invalid/kok");
    await page.getByLabel("Ort").fill("Göteborg");
    await page.getByLabel("Kontaktperson").fill("Anna Exempel");
    await page.getByLabel("Kontaktens e-post").fill("kontakt@example.invalid");
    await page
      .getByLabel(/Berättigat intresse/)
      .fill("B2B köksoffert — syntetisk E2E-fixture, ingen riktig kund.");

    await page.getByRole("button", { name: "Spara & analysera" }).click();

    // Fixture analysis landed via mock (no real HTML fetch / Places).
    await expect(
      page.getByRole("heading", { name: "Exempel Bygg AB" }).first(),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Svag väg till offert")).toBeVisible();
    await expect(page.getByText(/källbevis/i).first()).toBeVisible();

    await page.getByRole("button", { name: "Skapa kundupplägg" }).click();

    // Proposal preview tab.
    await expect(page.getByText("AGENTGENERERAT UTKAST")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("heading", { name: "Nytt webbupplägg för Exempel Bygg AB" }),
    ).toBeVisible();
    await expect(page.getByText("Tydligare offertväg")).toBeVisible();

    // Human review gate: approve stays disabled until all checks are ticked.
    await page.getByRole("button", { name: "Skapa e-post" }).click();
    await page.getByRole("button", { name: "Granska & godkänn" }).click();

    await expect(
      page.getByRole("heading", { name: /Godkänn leverans till Exempel Bygg AB/ }),
    ).toBeVisible();
    const approve = page.getByRole("button", { name: "Godkänn för leverans" });
    await expect(approve).toBeVisible();
    await expect(approve).toBeDisabled();

    // Places discovery stays locked; smoke never enables or clicks it.
    await expect(page.getByRole("button", { name: "Ny sökning" })).toBeDisabled();
  });
});
