/** Response contracts mirrored from services/api/app/prospecting/schemas.py. */

export interface ApiErrorBody {
  detail?: { message?: string; code?: string } | string;
  fields?: string[];
  request_id?: string;
}

export interface Summary {
  analyzed_sites: number;
  qualified_opportunities: number;
  awaiting_review: number;
  approved: number;
  potential_value_sek: number;
  suppressed_contacts: number;
  providers: Record<string, string | boolean>;
}

export interface Analysis {
  id: string;
  prospect_id: string;
  status: string;
  analyzed_url: string;
  final_url: string | null;
  improvement_score: number;
  performance_score: number;
  seo_score: number;
  accessibility_score: number;
  mobile_score: number;
  findings: Finding[];
  evidence: Evidence[];
  contact_candidates: ContactCandidate[];
  error_code: string | null;
  error_detail: string | null;
  created_at: string;
}

/** A contact fact read off the analysed page. A suggestion, never a verification. */
export interface ContactCandidate {
  field: "email" | "phone" | "company_name" | "org_number";
  value: string;
  confidence: number;
  source: string;
  evidence: string;
}

export interface Finding {
  title: string;
  detail?: string;
  severity?: string;
  confidence?: number;
}

export interface Evidence {
  label?: string;
  observed?: string;
  source?: string;
}

export interface Proposal {
  id: string;
  prospect_id: string;
  analysis_id: string;
  version: number;
  status: string;
  headline: string;
  summary: string;
  packages: ProposalPackage[];
  delivery_status: string;
  approved_at: string | null;
  share_expires_at: string | null;
  created_at: string;
}

export interface ProposalPackage {
  name: string;
  price_sek: number;
  recommended?: boolean;
  features?: string[];
}

export interface Prospect {
  id: string;
  company_name: string;
  website_url: string;
  normalized_domain: string;
  status: string;
  qualification_score: number;
  estimated_value_sek: number;
  contact_name: string | null;
  contact_email: string | null;
  contact_verified: boolean;
  contact_verification_source: string | null;
  do_not_contact: boolean;
  latest_analysis: Analysis | null;
  latest_proposal: Proposal | null;
  created_at: string;
}

export interface ShareCreated {
  proposal_id: string;
  token: string;
  public_path: string;
  presentation_path: string;
  expires_at: string;
}

export interface DeliveryResult {
  proposal_id: string;
  status: string;
  provider: string;
  external_sent: boolean;
  recipient: string;
  phase_disclaimer: string;
}
