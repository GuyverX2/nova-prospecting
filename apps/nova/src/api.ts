/**
 * Thin typed client for the Nova API.
 *
 * The console is served from the same origin as the API, so requests are
 * relative by default and no CORS grant is needed. The platform bearer token
 * is held in memory only: it is never written to localStorage, never put in a
 * URL, and never logged.
 */
import type {
  Analysis,
  ApiErrorBody,
  DeliveryResult,
  Proposal,
  Prospect,
  ShareCreated,
  Summary,
} from "./types";

declare global {
  interface Window {
    NOVA_PLATFORM_TOKEN?: string;
    NOVA_API_URL?: string;
  }
}

const configuredUrl = window.NOVA_API_URL ?? import.meta.env.VITE_NOVA_API_URL ?? "/api/v1";
export const apiUrl = configuredUrl.replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function describe(status: number, body: ApiErrorBody | null): ApiError {
  const detail = body?.detail;
  if (detail && typeof detail === "object") {
    const fields = body?.fields?.length ? ` (${body.fields.join(", ")})` : "";
    return new ApiError(
      status,
      detail.code ?? "UNKNOWN",
      `${detail.message ?? "Request failed"}${fields}`,
      body?.request_id,
    );
  }
  if (typeof detail === "string") {
    return new ApiError(status, "UNKNOWN", detail, body?.request_id);
  }
  return new ApiError(status, "UNKNOWN", `Request failed with status ${status}`);
}

async function request<T>(
  token: string,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      method: init.method ?? "GET",
      headers: {
        Authorization: `Bearer ${token.trim()}`,
        ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "The Nova API could not be reached.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }
  if (!response.ok) {
    throw describe(response.status, parsed as ApiErrorBody | null);
  }
  return parsed as T;
}

export const api = {
  summary: (token: string) => request<Summary>(token, "/prospecting/summary"),

  listProspects: (token: string, search: string) =>
    request<Prospect[]>(
      token,
      `/prospecting/prospects?limit=50${search ? `&search=${encodeURIComponent(search)}` : ""}`,
    ),

  createProspect: (
    token: string,
    payload: {
      company_name: string;
      website_url: string;
      contact_name?: string;
      contact_email?: string;
      estimated_value_sek?: number;
    },
  ) => request<Prospect>(token, "/prospecting/prospects", { method: "POST", body: payload }),

  verifyContact: (
    token: string,
    prospectId: string,
    payload: { contact_email?: string; contact_verified: boolean; contact_verification_source: string },
  ) => request<Prospect>(token, `/prospecting/prospects/${prospectId}`, { method: "PATCH", body: payload }),

  analyze: (token: string, prospectId: string, htmlSnapshot: string, allowFetch: boolean) =>
    request<Analysis>(token, `/prospecting/prospects/${prospectId}/analyses`, {
      method: "POST",
      body: htmlSnapshot.trim()
        ? { html_snapshot: htmlSnapshot }
        : { allow_network_fetch: allowFetch },
    }),

  generateProposal: (token: string, prospectId: string, analysisId: string) =>
    request<Proposal>(token, `/prospecting/prospects/${prospectId}/proposals`, {
      method: "POST",
      body: { analysis_id: analysisId },
    }),

  approveProposal: (
    token: string,
    proposalId: string,
    checks: {
      analysis_verified: boolean;
      contact_verified: boolean;
      content_approved: boolean;
      legal_basis_verified: boolean;
      reviewer_note?: string;
    },
  ) =>
    request<Proposal>(token, `/prospecting/proposals/${proposalId}/approve`, {
      method: "POST",
      body: checks,
    }),

  share: (token: string, proposalId: string) =>
    request<ShareCreated>(token, `/prospecting/proposals/${proposalId}/share`, {
      method: "POST",
      body: { expires_in_days: 14 },
    }),

  deliver: (token: string, proposalId: string, provider: string, testRecipient?: string) =>
    request<DeliveryResult>(token, `/prospecting/proposals/${proposalId}/deliver`, {
      method: "POST",
      body: testRecipient ? { provider, test_recipient: testRecipient } : { provider },
    }),

  suppress: (token: string, email: string) =>
    request<{ id: string }>(token, "/prospecting/suppressions", {
      method: "POST",
      body: { email, reason: "operator" },
    }),
};
