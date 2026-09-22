"""Persistent, tenant-scoped website prospecting domain models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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

    id = Column(String(32), primary_key=True, default=new_campaign_id)
    tenant_id = Column(String(255), nullable=False, index=True)
    created_by_subject = Column(String(255), nullable=False)
    name = Column(String(160), nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    mode = Column(String(32), nullable=False, default="manual_review")
    industry = Column(String(160), nullable=True)
    region = Column(String(160), nullable=True)
    employee_band = Column(String(64), nullable=True)
    min_score = Column(Integer, nullable=False, default=65)
    daily_limit = Column(Integer, nullable=False, default=20)
    criteria_json = Column(Text, nullable=False, default="{}")
    source_provider = Column(String(64), nullable=False, default="manual")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class WebsiteProspect(Base):
    __tablename__ = "website_prospects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_domain", name="uq_website_prospect_tenant_domain"),
        Index("ix_website_prospect_tenant_status", "tenant_id", "status"),
        Index("ix_website_prospect_tenant_score", "tenant_id", "qualification_score"),
    )

    id = Column(String(32), primary_key=True, default=new_prospect_id)
    tenant_id = Column(String(255), nullable=False, index=True)
    campaign_id = Column(String(32), ForeignKey("prospecting_campaigns.id"), nullable=True, index=True)
    assigned_subject = Column(String(255), nullable=True)
    company_name = Column(String(240), nullable=False)
    organization_number = Column(String(64), nullable=True)
    website_url = Column(String(2048), nullable=False)
    normalized_domain = Column(String(255), nullable=False)
    industry = Column(String(160), nullable=True)
    city = Column(String(120), nullable=True)
    employee_band = Column(String(64), nullable=True)
    turnover_label = Column(String(64), nullable=True)
    qualification_score = Column(Integer, nullable=False, default=0)
    estimated_value_sek = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="qualified")
    contact_name = Column(String(180), nullable=True)
    contact_role = Column(String(120), nullable=True)
    contact_email = Column(String(320), nullable=True)
    contact_verified = Column(Boolean, nullable=False, default=False)
    contact_verified_at = Column(DateTime, nullable=True)
    contact_verification_source = Column(String(512), nullable=True)
    legal_basis = Column(String(64), nullable=False, default="legitimate_interest_b2b")
    legitimate_interest_note = Column(Text, nullable=True)
    do_not_contact = Column(Boolean, nullable=False, default=False)
    retention_until = Column(DateTime, nullable=True)
    source_provider = Column(String(64), nullable=False, default="manual")
    source_url = Column(String(2048), nullable=True)
    source_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class WebsiteAnalysis(Base):
    __tablename__ = "website_analyses"
    __table_args__ = (
        Index("ix_website_analysis_prospect_created", "prospect_id", "created_at"),
        Index("ix_website_analysis_tenant_status", "tenant_id", "status"),
    )

    id = Column(String(32), primary_key=True, default=new_analysis_id)
    tenant_id = Column(String(255), nullable=False, index=True)
    prospect_id = Column(String(32), ForeignKey("website_prospects.id"), nullable=False, index=True)
    requested_by_subject = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    analyzer_version = Column(String(32), nullable=False, default="website-audit-v1")
    analyzed_url = Column(String(2048), nullable=False)
    final_url = Column(String(2048), nullable=True)
    improvement_score = Column(Integer, nullable=False, default=0)
    performance_score = Column(Integer, nullable=False, default=0)
    seo_score = Column(Integer, nullable=False, default=0)
    accessibility_score = Column(Integer, nullable=False, default=0)
    mobile_score = Column(Integer, nullable=False, default=0)
    findings_json = Column(Text, nullable=False, default="[]")
    evidence_json = Column(Text, nullable=False, default="[]")
    technical_json = Column(Text, nullable=False, default="{}")
    snapshot_sha256 = Column(String(64), nullable=True)
    fetch_duration_ms = Column(Integer, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class WebsiteProposal(Base):
    __tablename__ = "website_proposals"
    __table_args__ = (
        UniqueConstraint("prospect_id", "version", name="uq_website_proposal_prospect_version"),
        Index("ix_website_proposal_tenant_status", "tenant_id", "status"),
        Index("ix_website_proposal_share_hash", "share_token_hash"),
    )

    id = Column(String(32), primary_key=True, default=new_proposal_id)
    tenant_id = Column(String(255), nullable=False, index=True)
    prospect_id = Column(String(32), ForeignKey("website_prospects.id"), nullable=False, index=True)
    analysis_id = Column(String(32), ForeignKey("website_analyses.id"), nullable=False)
    created_by_subject = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="draft")
    headline = Column(String(300), nullable=False)
    summary = Column(Text, nullable=False)
    sitemap_json = Column(Text, nullable=False, default="[]")
    benefits_json = Column(Text, nullable=False, default="[]")
    packages_json = Column(Text, nullable=False, default="[]")
    timeline_json = Column(Text, nullable=False, default="[]")
    email_subject = Column(String(300), nullable=False)
    email_body = Column(Text, nullable=False)
    review_json = Column(Text, nullable=False, default="{}")
    approved_by_subject = Column(String(255), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    share_token_hash = Column(String(64), nullable=True)
    share_expires_at = Column(DateTime, nullable=True)
    delivery_status = Column(String(32), nullable=False, default="not_queued")
    delivery_provider = Column(String(64), nullable=True)
    delivery_id = Column(String(255), nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ProspectingPolicy(Base):
    __tablename__ = "prospecting_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_prospecting_policy_tenant"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    mode = Column(String(32), nullable=False, default="manual_review")
    auto_analyze = Column(Boolean, nullable=False, default=False)
    auto_generate_proposal = Column(Boolean, nullable=False, default=False)
    auto_queue_after_approval = Column(Boolean, nullable=False, default=False)
    minimum_score = Column(Integer, nullable=False, default=80)
    daily_delivery_limit = Column(Integer, nullable=False, default=20)
    updated_by_subject = Column(String(255), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ProspectSuppression(Base):
    __tablename__ = "prospect_suppressions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_email", name="uq_prospect_suppression_tenant_email"),
        Index("ix_prospect_suppression_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(String(32), primary_key=True, default=new_suppression_id)
    tenant_id = Column(String(255), nullable=False, index=True)
    prospect_id = Column(String(32), ForeignKey("website_prospects.id"), nullable=True)
    normalized_email = Column(String(320), nullable=False)
    reason = Column(String(64), nullable=False, default="opt_out")
    source = Column(String(64), nullable=False, default="public_opt_out")
    created_by_subject = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
