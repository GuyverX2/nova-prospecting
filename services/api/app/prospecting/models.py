"""Persistent, tenant-scoped website prospecting domain models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def new_campaign_id() -> str:
    return _id("pc")


def new_prospect_id() -> str:
    return _id("pr")


def new_analysis_id() -> str:
    return _id("wa")


def new_proposal_id() -> str:
    return _id("wp")


def new_suppression_id() -> str:
    return _id("ps")


class ProspectingCampaign(Base):
    __tablename__ = "prospecting_campaigns"
    __table_args__ = (
        Index("ix_prospecting_campaign_tenant_created", "tenant_id", "created_at"),
        Index("ix_prospecting_campaign_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_campaign_id)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_review")
    industry: Mapped[str | None] = mapped_column(String(160), nullable=True)
    region: Mapped[str | None] = mapped_column(String(160), nullable=True)
    employee_band: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_score: Mapped[int] = mapped_column(Integer, nullable=False, default=65)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WebsiteProspect(Base):
    __tablename__ = "website_prospects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_domain", name="uq_website_prospect_tenant_domain"),
        Index("ix_website_prospect_tenant_status", "tenant_id", "status"),
        Index("ix_website_prospect_tenant_score", "tenant_id", "qualification_score"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_prospect_id)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("prospecting_campaigns.id"), nullable=True, index=True
    )
    assigned_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str] = mapped_column(String(240), nullable=False)
    organization_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employee_band: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turnover_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qualification_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_value_sek: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="qualified")
    contact_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    contact_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contact_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    contact_verification_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    legal_basis: Mapped[str] = mapped_column(String(64), nullable=False, default="legitimate_interest_b2b")
    legitimate_interest_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WebsiteAnalysis(Base):
    __tablename__ = "website_analyses"
    __table_args__ = (
        Index("ix_website_analysis_prospect_created", "prospect_id", "created_at"),
        Index("ix_website_analysis_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_analysis_id)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prospect_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("website_prospects.id"), nullable=False, index=True
    )
    requested_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    analyzer_version: Mapped[str] = mapped_column(String(32), nullable=False, default="website-audit-v1")
    analyzed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    improvement_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    performance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seo_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accessibility_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mobile_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    technical_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    #: Provenance-carrying contact facts read off the analysed page. These are
    #: *suggestions for a human*, never a verification: promoting one into
    #: prospect.contact_email still requires the operator to say how they
    #: verified it (see service.update_prospect).
    contact_candidates_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetch_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class WebsiteProposal(Base):
    __tablename__ = "website_proposals"
    __table_args__ = (
        UniqueConstraint("prospect_id", "version", name="uq_website_proposal_prospect_version"),
        Index("ix_website_proposal_tenant_status", "tenant_id", "status"),
        Index("ix_website_proposal_share_hash", "share_token_hash"),
        Index("ix_website_proposal_tenant_delivery", "tenant_id", "delivery_processed_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_proposal_id)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prospect_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("website_prospects.id"), nullable=False, index=True
    )
    analysis_id: Mapped[str] = mapped_column(String(32), ForeignKey("website_analyses.id"), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sitemap_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    benefits_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    packages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    timeline_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    email_subject: Mapped[str] = mapped_column(String(300), nullable=False)
    email_body: Mapped[str] = mapped_column(Text, nullable=False)
    review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    approved_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    share_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    share_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_queued")
    delivery_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: When delivery was last accepted for this proposal (queued, mocked or
    #: really sent). Separate from ``updated_at`` so an unrelated edit cannot
    #: move a proposal in or out of the tenant's daily delivery window.
    delivery_processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProspectingPolicy(Base):
    __tablename__ = "prospecting_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_prospecting_policy_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_review")
    auto_analyze: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_generate_proposal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_queue_after_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    minimum_score: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    daily_delivery_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProspectSuppression(Base):
    __tablename__ = "prospect_suppressions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_email", name="uq_prospect_suppression_tenant_email"),
        Index("ix_prospect_suppression_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_suppression_id)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prospect_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("website_prospects.id"), nullable=True
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="opt_out")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="public_opt_out")
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
