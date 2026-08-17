import { resolveApiUrl } from "./apiBase";

export type ApiProspectingPolicy = {
  tenant_id: number;
  mode: "manual_review" | "rules_assisted";
  auto_analyze: boolean;
  auto_generate_proposal: boolean;
  auto_queue_after_approval: boolean;
  minimum_score: number;
  daily_delivery_limit: number;
  real_email_enabled: boolean;
  scheduler_enabled: boolean;
  updated_at: string | null;
};

export type ApiProspectingSummary = {
  analyzed_sites: number;
  qualified_opportunities: number;
  awaiting_review: number;
  approved: number;
  potential_value_sek: number;
  suppressed_contacts: number;
  providers: {
    discovery?: { provider?: string; configured?: boolean };
    website_fetch?: { enabled?: boolean };
    email?: { provider?: string; configured?: boolean; real_send_enabled?: boolean; from_addresses?: string[] };
  };
};

export type ApiAnalysis = {
  id: string;
  status: string;
  improvement_score: number;
  metrics: { performance: number; seo: number; accessibility: number; mobile: number };
  findings: Array<{
    key: string;
    title: string;
    detail: string;
    severity: "high" | "medium" | "positive";
    confidence: number;
    evidence_ids: string[];
  }>;
  evidence: Array<{ id: string; label: string; value: unknown; source: string; url: string }>;
  technical: Record<string, unknown>;
};

export type ApiProposal = {
  id: string;
  status: string;
  version: number;
  headline: string;
  summary: string;
  sitemap: string[];
  benefits: Array<{ title: string; detail: string }>;
  packages: Array<{ name: string; price_sek: number; recommended?: boolean; features: string[] }>;
  timeline: Array<{ week: string; title: string }>;
  email_subject: string;
  email_body: string;
  delivery_status: string;
};

export type ApiProspect = {
  id: string;
  campaign_id: string | null;
  company_name: string;
  organization_number: string | null;
  website_url: string;
  normalized_domain: string;
  industry: string | null;
  city: string | null;
  employee_band: string | null;
  turnover_label: string | null;
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
  latest_analysis?: ApiAnalysis | null;
  latest_proposal?: ApiProposal | null;
};

type ApiErrorBody = { detail?: string | { message?: string; code?: string } };

export class ProspectingApiError extends Error {
  status: number;
  code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ProspectingApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(apiBase: string, token: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolveApiUrl(apiBase, `/api/v1/prospecting${path}`), {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {})
    }
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = await response.json() as ApiErrorBody;
    } catch {
      // Fall through to the status text.
    }
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message || response.statusText || "API request failed";
    const code = typeof detail === "object" ? detail?.code || null : null;
    throw new ProspectingApiError(message, response.status, code);
  }
  return await response.json() as T;
}

export async function loadProspectingWorkspace(apiBase: string, token: string): Promise<{ summary: ApiProspectingSummary; prospects: ApiProspect[]; policy: ApiProspectingPolicy }> {
  const [summary, prospects, policy] = await Promise.all([
    request<ApiProspectingSummary>(apiBase, token, "/summary"),
    request<ApiProspect[]>(apiBase, token, "/prospects?limit=200"),
    request<ApiProspectingPolicy>(apiBase, token, "/policy")
  ]);
  return { summary, prospects, policy };
}

export function updateProspectingPolicy(apiBase: string, token: string, payload: Omit<ApiProspectingPolicy, "tenant_id" | "real_email_enabled" | "scheduler_enabled" | "updated_at">) {
  return request<ApiProspectingPolicy>(apiBase, token, "/policy", { method: "PATCH", body: JSON.stringify(payload) });
}

export function createCampaign(apiBase: string, token: string, payload: Record<string, unknown>) {
  return request<{ id: string }>(apiBase, token, "/campaigns", { method: "POST", body: JSON.stringify(payload) });
}

export function discoverCampaign(apiBase: string, token: string, campaignId: string, query: string, region?: string) {
  return request<{ created: ApiProspect[]; skipped: Array<Record<string, unknown>>; provider: string }>(apiBase, token, `/campaigns/${campaignId}/discover`, {
    method: "POST",
    body: JSON.stringify({ query, region: region || null, limit: 10 })
  });
}

export function createManualProspect(apiBase: string, token: string, payload: Record<string, unknown>) {
  return request<ApiProspect>(apiBase, token, "/prospects", { method: "POST", body: JSON.stringify(payload) });
}

export function updateProspect(apiBase: string, token: string, prospectId: string, payload: Record<string, unknown>) {
  return request<ApiProspect>(apiBase, token, `/prospects/${prospectId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function analyzeProspect(apiBase: string, token: string, prospectId: string, allowNetworkFetch = true) {
  return request<ApiAnalysis>(apiBase, token, `/prospects/${prospectId}/analyses`, {
    method: "POST",
    body: JSON.stringify({ allow_network_fetch: allowNetworkFetch })
  });
}

export function generateProposal(apiBase: string, token: string, prospectId: string, analysisId?: string) {
  return request<ApiProposal>(apiBase, token, `/prospects/${prospectId}/proposals`, {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId || null })
  });
}

export function updateProposal(apiBase: string, token: string, proposalId: string, payload: Record<string, unknown>) {
  return request<ApiProposal>(apiBase, token, `/proposals/${proposalId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function approveProposal(apiBase: string, token: string, proposalId: string, reviewerNote: string) {
  return request<ApiProposal>(apiBase, token, `/proposals/${proposalId}/approve`, {
    method: "POST",
    body: JSON.stringify({
      analysis_verified: true,
      contact_verified: true,
      content_approved: true,
      legal_basis_verified: true,
      reviewer_note: reviewerNote
    })
  });
}

export function createProposalShare(apiBase: string, token: string, proposalId: string) {
  return request<{ token: string; public_path: string; expires_at: string }>(apiBase, token, `/proposals/${proposalId}/share`, {
    method: "POST",
    body: JSON.stringify({ expires_in_days: 14 })
  });
}

export function queueProposalDelivery(
  apiBase: string,
  token: string,
  proposalId: string,
  provider: "queue" | "mock" | "resend" | "smtp_generic" = "queue",
  shareToken?: string,
  fromAddress?: string
) {
  return request<{ status: string; external_sent: boolean; delivery_id: string }>(apiBase, token, `/proposals/${proposalId}/deliver`, {
    method: "POST",
    body: JSON.stringify({ provider, share_token: shareToken || null, from_address: fromAddress || null })
  });
}

export function suppressProspect(apiBase: string, token: string, prospectId: string, email: string) {
  return request<{ id: string }>(apiBase, token, "/suppressions", {
    method: "POST",
    body: JSON.stringify({ prospect_id: prospectId, email, reason: "operator" })
  });
}
