"""API contracts for the website prospecting workflow."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    industry: str | None = Field(None, max_length=160)
    region: str | None = Field(None, max_length=160)
    employee_band: str | None = Field(None, max_length=64)
    min_score: int = Field(65, ge=0, le=100)
    daily_limit: int = Field(20, ge=1, le=200)
    mode: Literal["manual_review", "rules_assisted"] = "manual_review"
    source_provider: Literal["manual", "google_places"] = "manual"
    criteria: dict[str, Any] = Field(default_factory=dict)


class CampaignItem(BaseModel):
    id: str
    name: str
    status: str
    mode: str
    industry: str | None
    region: str | None
    employee_band: str | None
    min_score: int
    daily_limit: int
    source_provider: str
    criteria: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProspectCreate(BaseModel):
    campaign_id: str | None = None
    company_name: str = Field(..., min_length=2, max_length=240)
    organization_number: str | None = Field(None, max_length=64)
    website_url: str = Field(..., min_length=8, max_length=2048)
    industry: str | None = Field(None, max_length=160)
    city: str | None = Field(None, max_length=120)
    employee_band: str | None = Field(None, max_length=64)
    turnover_label: str | None = Field(None, max_length=64)
    qualification_score: int = Field(0, ge=0, le=100)
    estimated_value_sek: int = Field(0, ge=0, le=10_000_000)
    contact_name: str | None = Field(None, max_length=180)
    contact_role: str | None = Field(None, max_length=120)
    contact_email: str | None = Field(None, max_length=320)
    contact_verified: bool = False
    contact_verification_source: str | None = Field(None, max_length=512)
    legal_basis: Literal["legitimate_interest_b2b", "consent", "existing_customer"] = "legitimate_interest_b2b"
    legitimate_interest_note: str | None = Field(None, max_length=2000)
    retention_days: int = Field(180, ge=1, le=730)
    source_provider: str = Field("manual", max_length=64)
    source_url: str | None = Field(None, max_length=2048)

    @field_validator("website_url")
    @classmethod
    def validate_scheme(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("https://", "http://")):
            raise ValueError("website_url must use http or https")
        return value

    @field_validator("contact_email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("contact_email must be a valid email address")
        return normalized


class ProspectUpdate(BaseModel):
    assigned_user_id: int | None = None
    status: Literal["qualified", "analysis_ready", "proposal_ready", "approved", "contacted", "won", "lost"] | None = None
    contact_name: str | None = Field(None, max_length=180)
    contact_role: str | None = Field(None, max_length=120)
    contact_email: str | None = Field(None, max_length=320)
    contact_verified: bool | None = None
    contact_verification_source: str | None = Field(None, max_length=512)
    qualification_score: int | None = Field(None, ge=0, le=100)
    estimated_value_sek: int | None = Field(None, ge=0, le=10_000_000)
    do_not_contact: bool | None = None


class ProspectItem(BaseModel):
    id: str
    campaign_id: str | None
    company_name: str
    organization_number: str | None
    website_url: str
    normalized_domain: str
    industry: str | None
    city: str | None
    employee_band: str | None
    turnover_label: str | None
    qualification_score: int
    estimated_value_sek: int
    status: str
    contact_name: str | None
    contact_role: str | None
    contact_email: str | None
    contact_verified: bool
    legal_basis: str
    do_not_contact: bool
    retention_until: datetime | None
    source_provider: str
    source_url: str | None
    source_checked_at: datetime | None
    latest_analysis: dict[str, Any] | None = None
    latest_proposal: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisRequest(BaseModel):
    website_url: str | None = Field(None, max_length=2048)
    html_snapshot: str | None = Field(None, max_length=1_500_000)
    allow_network_fetch: bool = False


class AnalysisItem(BaseModel):
    id: str
    prospect_id: str
    status: str
    analyzer_version: str
    analyzed_url: str
    final_url: str | None
    improvement_score: int
    metrics: dict[str, int]
    findings: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    technical: dict[str, Any]
    snapshot_sha256: str | None
    fetch_duration_ms: int | None
    error_code: str | None
    error_detail: str | None
    analyzed_at: datetime | None
    created_at: datetime


class ProposalCreate(BaseModel):
    analysis_id: str | None = None
    package_currency: Literal["SEK"] = "SEK"


class ProposalUpdate(BaseModel):
    headline: str | None = Field(None, min_length=5, max_length=300)
    summary: str | None = Field(None, min_length=10, max_length=5000)
    sitemap: list[str] | None = Field(None, max_length=30)
    benefits: list[dict[str, Any]] | None = Field(None, max_length=20)
    packages: list[dict[str, Any]] | None = Field(None, max_length=10)
    timeline: list[dict[str, Any]] | None = Field(None, max_length=20)
    email_subject: str | None = Field(None, min_length=3, max_length=300)
    email_body: str | None = Field(None, min_length=20, max_length=20_000)


class ProposalReview(BaseModel):
    analysis_verified: bool
    contact_verified: bool
    content_approved: bool
    legal_basis_verified: bool
    reviewer_note: str | None = Field(None, max_length=2000)


class ProposalItem(BaseModel):
    id: str
    prospect_id: str
    analysis_id: str
    version: int
    status: str
    headline: str
    summary: str
    sitemap: list[str]
    benefits: list[dict[str, Any]]
    packages: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    email_subject: str
    email_body: str
    review: dict[str, Any]
    approved_by_user_id: int | None
    approved_at: datetime | None
    share_expires_at: datetime | None
    delivery_status: str
    delivery_provider: str | None
    delivery_id: str | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ShareCreate(BaseModel):
    expires_in_days: int = Field(14, ge=1, le=90)


class ShareCreated(BaseModel):
    proposal_id: str
    token: str
    public_path: str
    expires_at: datetime


class DeliveryRequest(BaseModel):
    provider: Literal["queue", "mock", "resend", "smtp_generic"] = "queue"
    test_recipient: str | None = Field(None, max_length=320)
    share_token: str | None = Field(None, min_length=20, max_length=200)
    from_address: str | None = Field(None, max_length=320)


class DeliveryResult(BaseModel):
    proposal_id: str
    status: str
    provider: str
    delivery_id: str | None
    external_sent: bool
    recipient: str
    phase_disclaimer: str


class DiscoveryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=240)
    region: str | None = Field(None, max_length=160)
    limit: int = Field(10, ge=1, le=20)


class SuppressionCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    reason: Literal["opt_out", "bounce", "complaint", "operator"] = "operator"
    prospect_id: str | None = None


class ProspectingPolicyUpdate(BaseModel):
    mode: Literal["manual_review", "rules_assisted"] = "manual_review"
    auto_analyze: bool = False
    auto_generate_proposal: bool = False
    auto_queue_after_approval: bool = False
    minimum_score: int = Field(80, ge=0, le=100)
    daily_delivery_limit: int = Field(20, ge=1, le=200)


class ProspectingPolicyItem(ProspectingPolicyUpdate):
    tenant_id: int
    real_email_enabled: bool
    scheduler_enabled: bool
    updated_at: datetime | None


class ProspectingSummary(BaseModel):
    analyzed_sites: int
    qualified_opportunities: int
    awaiting_review: int
    approved: int
    potential_value_sek: int
    suppressed_contacts: int
    providers: dict[str, Any]
