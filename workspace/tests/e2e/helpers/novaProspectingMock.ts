import type { Page, Route } from "@playwright/test";

/**
 * Synthetic fixture HTML for N1-7 — never fetched from a real host.
 * Evidence payloads reference this string only; Places / prod scrape are STOP.
 */
export const NOVA_FIXTURE_HTML = `<!DOCTYPE html>
<html lang="sv">
<head><meta charset="utf-8"><title>Exempel Bygg AB — kök</title></head>
<body>
  <h1>Exempel Bygg AB</h1>
  <p>Köksrenovering i Göteborg. Ring oss för offert.</p>
  <a href="/kontakt">Kontakt</a>
</body>
</html>`;

const FIXTURE_URL = "https://example.invalid/kok";
const FIXTURE_DOMAIN = "example.invalid";
const PROSPECT_ID = "e2e-nova-prospect-001";
const ANALYSIS_ID = "e2e-nova-analysis-001";
const PROPOSAL_ID = "e2e-nova-proposal-001";

type MockProspect = {
  id: string;
  campaign_id: null;
  company_name: string;
  organization_number: null;
  website_url: string;
  normalized_domain: string;
  industry: string | null;
  city: string | null;
  employee_band: null;
  turnover_label: null;
  qualification_score: number;
  estimated_value_sek: number;
  status: string;
  contact_name: string | null;
  contact_role: string | null;
  contact_email: string | null;
  contact_verified: boolean;
  legal_basis: string;
  do_not_contact: boolean;
  source_provider: string;
  source_url: string | null;
  latest_analysis: ReturnType<typeof buildAnalysis> | null;
  latest_proposal: ReturnType<typeof buildProposal> | null;
};

function buildAnalysis() {
  return {
    id: ANALYSIS_ID,
    status: "complete",
    improvement_score: 78,
    metrics: { performance: 42, seo: 55, accessibility: 61, mobile: 38 },
    findings: [
      {
        key: "cta_missing",
        title: "Svag väg till offert",
        detail: "Startsida saknar tydlig CTA till kontaktformulär (fixture HTML).",
        severity: "high" as const,
        confidence: 0.91,
        evidence_ids: ["ev-title"],
      },
      {
        key: "mobile_viewport",
        title: "Mobilviewport saknas",
        detail: "Ingen viewport-meta i den mockade HTML-fixturen.",
        severity: "medium" as const,
        confidence: 0.88,
        evidence_ids: ["ev-html"],
      },
    ],
    evidence: [
      {
        id: "ev-title",
        label: "Sidtitel",
        value: "Exempel Bygg AB — kök",
        source: "fixture_html",
        url: FIXTURE_URL,
      },
      {
        id: "ev-html",
        label: "Fixture HTML (syntetisk)",
        value: NOVA_FIXTURE_HTML.slice(0, 120) + "…",
        source: "fixture_html",
        url: FIXTURE_URL,
      },
    ],
    technical: {
      fetch_mode: "fixture_mock",
      content_type: "text/html",
      bytes: NOVA_FIXTURE_HTML.length,
    },
  };
}

function buildProposal(company: string) {
  return {
    id: PROPOSAL_ID,
    status: "draft",
    version: 1,
    headline: `Nytt webbupplägg för ${company}`,
    summary: `Syntetiskt kundupplägg från fixture-analys av ${FIXTURE_DOMAIN}.`,
    sitemap: ["Start", "Tjänster", "Projekt", "Om oss", "Kontakt", "Offert"],
    benefits: [
      {
        title: "Tydligare offertväg",
        detail: "CTA och formulär baserat på fixture-observationer.",
      },
      {
        title: "Mobil först",
        detail: "Viewport och laddning förbättras innan utskick.",
      },
    ],
    packages: [
      {
        name: "Grund",
        price_sek: 45000,
        recommended: true,
        features: ["Startsida", "Kontakt", "Mobil"],
      },
    ],
    timeline: [
      { week: "Vecka 1–2", title: "Innehåll & wireframes" },
      { week: "Vecka 3–4", title: "Bygg & QA" },
    ],
    email_subject: `3 konkreta förbättringar för ${FIXTURE_DOMAIN}`,
    email_body: `Hej,\n\nVi tittade på ${FIXTURE_DOMAIN} (syntetisk fixture) och såg förbättringsmöjligheter.\n\nVänliga hälsningar,\nNova E2E`,
    delivery_status: "not_sent",
  };
}

function emptySummary(prospectCount: number) {
  return {
    analyzed_sites: prospectCount,
    qualified_opportunities: prospectCount,
    awaiting_review: prospectCount,
    approved: 0,
    potential_value_sek: prospectCount ? 120_000 : 0,
    suppressed_contacts: 0,
    providers: {
      discovery: { provider: "disabled", configured: false },
      website_fetch: { enabled: true },
      email: {
        provider: "disabled",
        configured: false,
        real_send_enabled: false,
        from_addresses: [] as string[],
      },
    },
  };
}

const POLICY = {
  tenant_id: 1,
  mode: "manual_review" as const,
  auto_analyze: false,
  auto_generate_proposal: false,
  auto_queue_after_approval: false,
  minimum_score: 65,
  daily_delivery_limit: 20,
  real_email_enabled: false,
  scheduler_enabled: false,
  updated_at: null,
};

async function json(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * Intercept `/api/v1/prospecting/*` with a stateful synthetic workspace.
 * Login/auth stay on the real demo API. No Places, no real HTML fetch, no send.
 */
export async function installNovaProspectingMocks(page: Page): Promise<{
  getProspectCount: () => number;
}> {
  const prospects: MockProspect[] = [];

  await page.route("**/api/v1/prospecting/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname.replace(/\/+$/, "");
    const prospectingPath = path.split("/api/v1/prospecting")[1] || "/";

    if (method === "GET" && prospectingPath === "/summary") {
      return json(route, 200, emptySummary(prospects.length));
    }
    if (method === "GET" && prospectingPath === "/policy") {
      return json(route, 200, POLICY);
    }
    if (method === "GET" && prospectingPath.startsWith("/prospects")) {
      return json(route, 200, prospects);
    }

    if (method === "POST" && prospectingPath === "/prospects") {
      const payload = request.postDataJSON() as {
        company_name?: string;
        website_url?: string;
        contact_name?: string | null;
        contact_email?: string | null;
        city?: string | null;
      };
      const company = (payload.company_name || "Exempel Bygg AB").trim();
      const website = (payload.website_url || FIXTURE_URL).trim();
      const prospect: MockProspect = {
        id: PROSPECT_ID,
        campaign_id: null,
        company_name: company,
        organization_number: null,
        website_url: website,
        normalized_domain: FIXTURE_DOMAIN,
        industry: "Bygg & hantverk",
        city: payload.city || "Göteborg",
        employee_band: null,
        turnover_label: null,
        qualification_score: 70,
        estimated_value_sek: 120_000,
        status: "qualified",
        contact_name: payload.contact_name || "Anna Exempel",
        contact_role: "VD",
        contact_email: payload.contact_email || "kontakt@example.invalid",
        contact_verified: false,
        legal_basis: "legitimate_interest_b2b",
        do_not_contact: false,
        source_provider: "manual",
        source_url: website,
        latest_analysis: null,
        latest_proposal: null,
      };
      prospects.length = 0;
      prospects.push(prospect);
      return json(route, 200, prospect);
    }

    const analysisMatch = prospectingPath.match(
      /^\/prospects\/([^/]+)\/analyses$/,
    );
    if (method === "POST" && analysisMatch) {
      const prospect = prospects.find((p) => p.id === analysisMatch[1]);
      if (!prospect) {
        return json(route, 404, {
          detail: { code: "PROSPECT_NOT_FOUND", message: "Unknown prospect" },
        });
      }
      const analysis = buildAnalysis();
      prospect.latest_analysis = analysis;
      prospect.status = "analysis_ready";
      return json(route, 200, analysis);
    }

    const proposalMatch = prospectingPath.match(
      /^\/prospects\/([^/]+)\/proposals$/,
    );
    if (method === "POST" && proposalMatch) {
      const prospect = prospects.find((p) => p.id === proposalMatch[1]);
      if (!prospect) {
        return json(route, 404, {
          detail: { code: "PROSPECT_NOT_FOUND", message: "Unknown prospect" },
        });
      }
      const proposal = buildProposal(prospect.company_name);
      prospect.latest_proposal = proposal;
      prospect.status = "proposal_ready";
      return json(route, 200, proposal);
    }

    // Fail closed on unexpected prospecting writes (deliver / approve / discover).
    if (method !== "GET") {
      return json(route, 403, {
        detail: {
          code: "E2E_MOCK_DENIED",
          message: `Nova E2E mock does not allow ${method} ${prospectingPath}`,
        },
      });
    }

    return json(route, 404, {
      detail: { code: "E2E_MOCK_NOT_FOUND", message: prospectingPath },
    });
  });

  return {
    getProspectCount: () => prospects.length,
  };
}
