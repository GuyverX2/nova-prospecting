"""Tenant-scoped website prospecting orchestration and state transitions."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.prospecting.analyzer import WebsiteAuditError, analyze_html, fetch_public_html, normalize_public_url
from app.prospecting.discovery import DiscoveryProviderError, discover_companies, provider_status
from app.prospecting.models import (
    ProspectSuppression,
    ProspectingCampaign,
    ProspectingPolicy,
    WebsiteAnalysis,
    WebsiteProposal,
    WebsiteProspect,
    new_analysis_id,
    new_campaign_id,
    new_proposal_id,
    new_prospect_id,
    new_suppression_id,
)
from app.prospecting.outbound import (
    ProspectingDeliveryError,
    deliver_email,
    opt_out_token,
    verify_opt_out_token,
)
from app.prospecting.pagespeed import PageSpeedError, run_pagespeed
from app.prospecting.schemas import (
    AnalysisRequest,
    CampaignCreate,
    DeliveryRequest,
    ProspectCreate,
    ProspectUpdate,
    ProspectingPolicyUpdate,
    ProposalReview,
    ProposalUpdate,
    SuppressionCreate,
)
from app.tenancy.service import TenantContext, record_audit


class ProspectingError(Exception):
    def __init__(self, status_code: int, detail: str, *, code: str = "PROSPECTING_ERROR"):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _now() -> datetime:
    return datetime.utcnow()


def _domain(url: str) -> str:
    parsed = urlsplit(normalize_public_url(url))
    hostname = (parsed.hostname or "").lower().strip(".")
    return hostname[4:] if hostname.startswith("www.") else hostname


def _audit(db: Session, ctx: TenantContext, user: User, action: str, target_type: str, target_id: str, request_id: str | None, after: dict | None = None) -> None:
    record_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_user_id=user.id,
        action_type=action,
        target_type=target_type,
        target_id=target_id,
        tenant_profile_id=ctx.active_profile_id,
        request_id=request_id,
        after=after,
    )


def _require_write(ctx: TenantContext) -> None:
    if not ctx.can_write():
        raise ProspectingError(403, "Write access is required for website prospecting", code="PROSPECTING_WRITE_FORBIDDEN")


def campaign_dict(row: ProspectingCampaign) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "mode": row.mode,
        "industry": row.industry,
        "region": row.region,
        "employee_band": row.employee_band,
        "min_score": row.min_score,
        "daily_limit": row.daily_limit,
        "source_provider": row.source_provider,
        "criteria": _load(row.criteria_json, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def analysis_dict(row: WebsiteAnalysis) -> dict:
    return {
        "id": row.id,
        "prospect_id": row.prospect_id,
        "status": row.status,
        "analyzer_version": row.analyzer_version,
        "analyzed_url": row.analyzed_url,
        "final_url": row.final_url,
        "improvement_score": row.improvement_score,
        "metrics": {
            "performance": row.performance_score,
            "seo": row.seo_score,
            "accessibility": row.accessibility_score,
            "mobile": row.mobile_score,
        },
        "findings": _load(row.findings_json, []),
        "evidence": _load(row.evidence_json, []),
        "technical": _load(row.technical_json, {}),
        "snapshot_sha256": row.snapshot_sha256,
        "fetch_duration_ms": row.fetch_duration_ms,
        "error_code": row.error_code,
        "error_detail": row.error_detail,
        "analyzed_at": row.analyzed_at,
        "created_at": row.created_at,
    }


def proposal_dict(row: WebsiteProposal) -> dict:
    return {
        "id": row.id,
        "prospect_id": row.prospect_id,
        "analysis_id": row.analysis_id,
        "version": row.version,
        "status": row.status,
        "headline": row.headline,
        "summary": row.summary,
        "sitemap": _load(row.sitemap_json, []),
        "benefits": _load(row.benefits_json, []),
        "packages": _load(row.packages_json, []),
        "timeline": _load(row.timeline_json, []),
        "email_subject": row.email_subject,
        "email_body": row.email_body,
        "review": _load(row.review_json, {}),
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at,
        "share_expires_at": row.share_expires_at,
        "delivery_status": row.delivery_status,
        "delivery_provider": row.delivery_provider,
        "delivery_id": row.delivery_id,
        "delivered_at": row.delivered_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def prospect_dict(db: Session, row: WebsiteProspect, *, include_latest: bool = True) -> dict:
    latest_analysis = None
    latest_proposal = None
    if include_latest:
        analysis = (
            db.query(WebsiteAnalysis)
            .filter(WebsiteAnalysis.tenant_id == row.tenant_id, WebsiteAnalysis.prospect_id == row.id)
            .order_by(WebsiteAnalysis.created_at.desc())
            .first()
        )
        proposal = (
            db.query(WebsiteProposal)
            .filter(WebsiteProposal.tenant_id == row.tenant_id, WebsiteProposal.prospect_id == row.id)
            .order_by(WebsiteProposal.version.desc())
            .first()
        )
        latest_analysis = analysis_dict(analysis) if analysis else None
        latest_proposal = proposal_dict(proposal) if proposal else None
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "company_name": row.company_name,
        "organization_number": row.organization_number,
        "website_url": row.website_url,
        "normalized_domain": row.normalized_domain,
        "industry": row.industry,
        "city": row.city,
        "employee_band": row.employee_band,
        "turnover_label": row.turnover_label,
        "qualification_score": row.qualification_score,
        "estimated_value_sek": row.estimated_value_sek,
        "status": row.status,
        "contact_name": row.contact_name,
        "contact_role": row.contact_role,
        "contact_email": row.contact_email,
        "contact_verified": row.contact_verified,
        "legal_basis": row.legal_basis,
        "do_not_contact": row.do_not_contact,
        "retention_until": row.retention_until,
        "source_provider": row.source_provider,
        "source_url": row.source_url,
        "source_checked_at": row.source_checked_at,
        "latest_analysis": latest_analysis,
        "latest_proposal": latest_proposal,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def create_campaign(db: Session, ctx: TenantContext, user: User, payload: CampaignCreate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = ProspectingCampaign(
        id=new_campaign_id(),
        tenant_id=ctx.tenant_id,
        created_by_user_id=user.id,
        name=payload.name.strip(),
        status="active",
        mode=payload.mode,
        industry=payload.industry,
        region=payload.region,
        employee_band=payload.employee_band,
        min_score=payload.min_score,
        daily_limit=payload.daily_limit,
        criteria_json=_json(payload.criteria),
        source_provider=payload.source_provider,
    )
    db.add(row)
    _audit(db, ctx, user, "prospecting.campaign_created", "prospecting_campaign", row.id, request_id, {"mode": row.mode, "provider": row.source_provider})
    db.commit()
    db.refresh(row)
    return campaign_dict(row)


def list_campaigns(db: Session, ctx: TenantContext) -> list[dict]:
    rows = db.query(ProspectingCampaign).filter(ProspectingCampaign.tenant_id == ctx.tenant_id).order_by(ProspectingCampaign.created_at.desc()).all()
    return [campaign_dict(row) for row in rows]


def _require_campaign(db: Session, ctx: TenantContext, campaign_id: str) -> ProspectingCampaign:
    row = db.query(ProspectingCampaign).filter(ProspectingCampaign.tenant_id == ctx.tenant_id, ProspectingCampaign.id == campaign_id).first()
    if row is None:
        raise ProspectingError(404, "Campaign not found", code="CAMPAIGN_NOT_FOUND")
    return row


def create_prospect(db: Session, ctx: TenantContext, user: User, payload: ProspectCreate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    if payload.campaign_id:
        _require_campaign(db, ctx, payload.campaign_id)
    domain = _domain(payload.website_url)
    duplicate = db.query(WebsiteProspect).filter(WebsiteProspect.tenant_id == ctx.tenant_id, WebsiteProspect.normalized_domain == domain).first()
    if duplicate:
        raise ProspectingError(409, "A prospect with this domain already exists", code="PROSPECT_DOMAIN_DUPLICATE")
    if payload.contact_verified and not payload.contact_email:
        raise ProspectingError(422, "A contact email is required before contact verification", code="CONTACT_EMAIL_REQUIRED")
    now = _now()
    row = WebsiteProspect(
        id=new_prospect_id(),
        tenant_id=ctx.tenant_id,
        campaign_id=payload.campaign_id,
        assigned_user_id=user.id,
        company_name=payload.company_name.strip(),
        organization_number=payload.organization_number,
        website_url=normalize_public_url(payload.website_url),
        normalized_domain=domain,
        industry=payload.industry,
        city=payload.city,
        employee_band=payload.employee_band,
        turnover_label=payload.turnover_label,
        qualification_score=payload.qualification_score,
        estimated_value_sek=payload.estimated_value_sek,
        status="qualified",
        contact_name=payload.contact_name,
        contact_role=payload.contact_role,
        contact_email=payload.contact_email,
        contact_verified=payload.contact_verified,
        contact_verified_at=now if payload.contact_verified else None,
        contact_verification_source=payload.contact_verification_source,
        legal_basis=payload.legal_basis,
        legitimate_interest_note=payload.legitimate_interest_note,
        retention_until=now + timedelta(days=payload.retention_days),
        source_provider=payload.source_provider,
        source_url=payload.source_url,
        source_checked_at=now,
    )
    db.add(row)
    _audit(db, ctx, user, "prospecting.prospect_created", "website_prospect", row.id, request_id, {"domain": domain, "source_provider": row.source_provider})
    db.commit()
    db.refresh(row)
    return prospect_dict(db, row)


def list_prospects(db: Session, ctx: TenantContext, *, status: str | None = None, search: str | None = None, limit: int = 100) -> list[dict]:
    query = db.query(WebsiteProspect).filter(WebsiteProspect.tenant_id == ctx.tenant_id)
    if status:
        query = query.filter(WebsiteProspect.status == status)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(WebsiteProspect.company_name).like(term) | func.lower(WebsiteProspect.normalized_domain).like(term))
    rows = query.order_by(WebsiteProspect.qualification_score.desc(), WebsiteProspect.created_at.desc()).limit(limit).all()
    return [prospect_dict(db, row, include_latest=False) for row in rows]


def require_prospect(db: Session, ctx: TenantContext, prospect_id: str) -> WebsiteProspect:
    row = db.query(WebsiteProspect).filter(WebsiteProspect.tenant_id == ctx.tenant_id, WebsiteProspect.id == prospect_id).first()
    if row is None:
        raise ProspectingError(404, "Prospect not found", code="PROSPECT_NOT_FOUND")
    return row


def update_prospect(db: Session, ctx: TenantContext, user: User, prospect_id: str, payload: ProspectUpdate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = require_prospect(db, ctx, prospect_id)
    changes = payload.model_dump(exclude_unset=True)
    if "contact_email" in changes and changes["contact_email"]:
        email = str(changes["contact_email"]).strip().lower()
        if "@" not in email:
            raise ProspectingError(422, "contact_email must be valid", code="CONTACT_EMAIL_INVALID")
        changes["contact_email"] = email
    if changes.get("contact_verified") and not changes.get("contact_email", row.contact_email):
        raise ProspectingError(422, "A contact email is required before contact verification", code="CONTACT_EMAIL_REQUIRED")
    for key, value in changes.items():
        setattr(row, key, value)
    if "contact_verified" in changes:
        row.contact_verified_at = _now() if changes["contact_verified"] else None
    if changes.get("do_not_contact") and row.contact_email:
        _upsert_suppression(db, ctx.tenant_id, row.contact_email, "operator", "operator", row.id, user.id)
    row.updated_at = _now()
    _audit(db, ctx, user, "prospecting.prospect_updated", "website_prospect", row.id, request_id, {"fields": sorted(changes)})
    db.commit()
    db.refresh(row)
    return prospect_dict(db, row)


def _merge_pagespeed(result: dict, pagespeed: dict) -> None:
    scores = pagespeed.get("scores") or {}
    for metric in ("performance", "seo", "accessibility"):
        value = scores.get(metric)
        if isinstance(value, int):
            result["metrics"][metric] = max(0, min(100, value))
    result["metrics"]["mobile"] = round((result["metrics"]["performance"] + result["metrics"]["accessibility"]) / 2)
    evidence_id = "ev_pagespeed_mobile"
    result["evidence"].append({
        "id": evidence_id,
        "label": "Google PageSpeed mobile lab result",
        "value": {"scores": scores, "web_vitals": pagespeed.get("web_vitals")},
        "source": "google_pagespeed_insights",
        "url": result["final_url"],
    })
    performance = result["metrics"]["performance"]
    if performance < 50 and not any(item.get("key") == "pagespeed_performance" for item in result["findings"]):
        result["findings"].insert(0, {
            "key": "pagespeed_performance",
            "title": "Låg mobilprestanda i Lighthouse",
            "detail": f"PageSpeed Insights gav {performance}/100 i det mobila labbtestet. Web Vitals och resursladdning bör prioriteras.",
            "severity": "high",
            "evidence_ids": [evidence_id],
            "confidence": 0.98,
        })
    result["technical"]["pagespeed"] = pagespeed
    result["technical"]["limitations"] = [
        item for item in result["technical"].get("limitations", [])
        if "Core Web Vitals require" not in item
    ]
    result["improvement_score"] = max(
        result["improvement_score"],
        round(100 - sum(result["metrics"].values()) / len(result["metrics"])),
    )


def run_analysis(db: Session, ctx: TenantContext, user: User, prospect_id: str, payload: AnalysisRequest, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    prospect = require_prospect(db, ctx, prospect_id)
    url = normalize_public_url(payload.website_url or prospect.website_url)
    row = WebsiteAnalysis(
        id=new_analysis_id(),
        tenant_id=ctx.tenant_id,
        prospect_id=prospect.id,
        requested_by_user_id=user.id,
        status="running",
        analyzed_url=url,
    )
    db.add(row)
    db.flush()
    try:
        if payload.html_snapshot is not None:
            result = analyze_html(payload.html_snapshot, url)
        else:
            if not payload.allow_network_fetch:
                raise WebsiteAuditError("NETWORK_FETCH_CONFIRMATION_REQUIRED", "Set allow_network_fetch=true to confirm this operator-selected public URL")
            if not settings.PROSPECTING_FETCH_ENABLED:
                raise WebsiteAuditError("WEBSITE_FETCH_DISABLED", "Public website fetching is disabled by the operator kill switch", 409)
            html, final_url, duration_ms, snapshot_hash = fetch_public_html(url)
            result = analyze_html(html, url, final_url=final_url, fetch_duration_ms=duration_ms)
            result["snapshot_sha256"] = snapshot_hash
            try:
                pagespeed = run_pagespeed(result["final_url"])
                if pagespeed:
                    _merge_pagespeed(result, pagespeed)
            except PageSpeedError as exc:
                result["technical"]["pagespeed_warning"] = str(exc)
        metrics = result["metrics"]
        row.status = "complete"
        row.final_url = result["final_url"]
        row.improvement_score = result["improvement_score"]
        row.performance_score = metrics["performance"]
        row.seo_score = metrics["seo"]
        row.accessibility_score = metrics["accessibility"]
        row.mobile_score = metrics["mobile"]
        row.findings_json = _json(result["findings"])
        row.evidence_json = _json(result["evidence"])
        row.technical_json = _json(result["technical"])
        row.snapshot_sha256 = result["snapshot_sha256"]
        row.fetch_duration_ms = result["fetch_duration_ms"]
        row.analyzed_at = _now()
        prospect.qualification_score = max(prospect.qualification_score, row.improvement_score)
        prospect.status = "analysis_ready"
        prospect.updated_at = _now()
    except WebsiteAuditError as exc:
        row.status = "failed"
        row.error_code = exc.code
        row.error_detail = exc.detail
        db.commit()
        raise ProspectingError(exc.status_code, exc.detail, code=exc.code) from exc
    _audit(db, ctx, user, "prospecting.analysis_completed", "website_analysis", row.id, request_id, {"prospect_id": prospect.id, "score": row.improvement_score, "evidence_count": len(result["evidence"])})
    db.commit()
    db.refresh(row)
    return analysis_dict(row)


def _latest_complete_analysis(db: Session, ctx: TenantContext, prospect_id: str, analysis_id: str | None = None) -> WebsiteAnalysis:
    query = db.query(WebsiteAnalysis).filter(WebsiteAnalysis.tenant_id == ctx.tenant_id, WebsiteAnalysis.prospect_id == prospect_id, WebsiteAnalysis.status == "complete")
    if analysis_id:
        query = query.filter(WebsiteAnalysis.id == analysis_id)
    row = query.order_by(WebsiteAnalysis.created_at.desc()).first()
    if row is None:
        raise ProspectingError(409, "A completed evidence-backed analysis is required", code="ANALYSIS_REQUIRED")
    return row


def generate_proposal(db: Session, ctx: TenantContext, user: User, prospect_id: str, analysis_id: str | None = None, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    prospect = require_prospect(db, ctx, prospect_id)
    analysis = _latest_complete_analysis(db, ctx, prospect.id, analysis_id)
    current_max = db.query(func.max(WebsiteProposal.version)).filter(WebsiteProposal.prospect_id == prospect.id).scalar() or 0
    findings = _load(analysis.findings_json, [])
    top_findings = [item["title"] for item in findings if item.get("severity") != "positive"][:3]
    first_name = (prospect.contact_name or "").split(" ")[0] or ""
    opportunity = max(prospect.estimated_value_sek, 32_000)
    packages = [
        {"name": "Bas", "price_sek": round(opportunity * 0.72 / 1000) * 1000, "features": ["Ny responsiv webbplats", "Grundläggande SEO", "Kontaktflöde"]},
        {"name": "Tillväxt", "price_sek": opportunity, "recommended": True, "features": ["Allt i Bas", "Lokala landningssidor", "Mätning och mötesbokning", "Innehållsstöd"]},
        {"name": "Premium", "price_sek": round(opportunity * 1.45 / 1000) * 1000, "features": ["Allt i Tillväxt", "Automatiserade leadflöden", "Löpande optimering", "Utökad innehållsplan"]},
    ]
    summary = f"Ett snabbare, tydligare och mätbart webbupplägg för {prospect.company_name}. Analysen prioriterar {', '.join(top_findings).lower() if top_findings else 'konvertering, synlighet och tillgänglighet'}."
    email_body = (
        f"Hej {first_name or 'där'},\n\n"
        f"Jag har tittat på {prospect.normalized_domain} och identifierat några konkreta möjligheter att göra webbplatsen tydligare, snabbare och bättre på att skapa relevanta förfrågningar.\n\n"
        f"De viktigaste områdena är {', '.join(top_findings).lower() if top_findings else 'mobilupplevelse, synlighet och kontaktvägar'}. Alla observationer i genomgången har ett sparat källunderlag.\n\n"
        "Jag har därför tagit fram ett kort förslag på ett nytt upplägg. Passar ett 20-minuters möte nästa vecka så går vi igenom det tillsammans?\n\n"
        "Vänliga hälsningar,\nSalesOS Webbstudio"
    )
    row = WebsiteProposal(
        id=new_proposal_id(),
        tenant_id=ctx.tenant_id,
        prospect_id=prospect.id,
        analysis_id=analysis.id,
        created_by_user_id=user.id,
        version=current_max + 1,
        status="draft",
        headline=f"Ett nytt digitalt upplägg för {prospect.company_name}",
        summary=summary,
        sitemap_json=_json(["Start", "Tjänster", "Referenser", "Om företaget", "Kunskap", "Kontakt", "Offert"]),
        benefits_json=_json([
            {"title": "Fler relevanta förfrågningar", "detail": "Tydliga kundresor och kvalificerande kontaktvägar."},
            {"title": "Mindre manuellt arbete", "detail": "Bokning, formulär och uppföljning kopplas till ett sammanhållet flöde."},
            {"title": "Starkare lokal synlighet", "detail": "Teknisk struktur och innehåll per prioriterat område."},
        ]),
        packages_json=_json(packages),
        timeline_json=_json([
            {"week": "1", "title": "Strategi och underlag"},
            {"week": "2–3", "title": "Design och innehåll"},
            {"week": "4–5", "title": "Utveckling och integration"},
            {"week": "6", "title": "Kvalitetssäkring och lansering"},
        ]),
        email_subject=f"3 konkreta förbättringar för {prospect.normalized_domain}",
        email_body=email_body,
    )
    db.add(row)
    prospect.status = "proposal_ready"
    prospect.updated_at = _now()
    _audit(db, ctx, user, "prospecting.proposal_generated", "website_proposal", row.id, request_id, {"prospect_id": prospect.id, "analysis_id": analysis.id, "version": row.version})
    db.commit()
    db.refresh(row)
    return proposal_dict(row)


def require_proposal(db: Session, ctx: TenantContext, proposal_id: str) -> WebsiteProposal:
    row = db.query(WebsiteProposal).filter(WebsiteProposal.tenant_id == ctx.tenant_id, WebsiteProposal.id == proposal_id).first()
    if row is None:
        raise ProspectingError(404, "Proposal not found", code="PROPOSAL_NOT_FOUND")
    return row


def update_proposal(db: Session, ctx: TenantContext, user: User, proposal_id: str, payload: ProposalUpdate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = require_proposal(db, ctx, proposal_id)
    if row.status == "approved":
        raise ProspectingError(409, "Approved proposals are immutable; create a new version", code="APPROVED_PROPOSAL_IMMUTABLE")
    mapping = {"sitemap": "sitemap_json", "benefits": "benefits_json", "packages": "packages_json", "timeline": "timeline_json"}
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        target = mapping.get(key, key)
        setattr(row, target, _json(value) if key in mapping else value)
    row.updated_at = _now()
    _audit(db, ctx, user, "prospecting.proposal_updated", "website_proposal", row.id, request_id, {"fields": sorted(changes)})
    db.commit()
    db.refresh(row)
    return proposal_dict(row)


def _is_suppressed(db: Session, tenant_id: int, email: str) -> bool:
    return db.query(ProspectSuppression).filter(ProspectSuppression.tenant_id == tenant_id, ProspectSuppression.normalized_email == email.strip().lower()).first() is not None


def approve_proposal(db: Session, ctx: TenantContext, user: User, proposal_id: str, review: ProposalReview, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = require_proposal(db, ctx, proposal_id)
    prospect = require_prospect(db, ctx, row.prospect_id)
    checks = review.model_dump()
    required = [review.analysis_verified, review.contact_verified, review.content_approved, review.legal_basis_verified]
    if not all(required):
        raise ProspectingError(422, "All four human verification checks are required", code="HUMAN_VERIFICATION_INCOMPLETE")
    if not prospect.contact_verified or not prospect.contact_email:
        raise ProspectingError(409, "The recipient contact must be verified before approval", code="CONTACT_NOT_VERIFIED")
    if prospect.do_not_contact or _is_suppressed(db, ctx.tenant_id, prospect.contact_email):
        raise ProspectingError(409, "The contact is on the suppression list", code="CONTACT_SUPPRESSED")
    analysis = _latest_complete_analysis(db, ctx, prospect.id, row.analysis_id)
    if not analysis.evidence_json or len(_load(analysis.evidence_json, [])) < 1:
        raise ProspectingError(409, "The analysis has no evidence packet", code="ANALYSIS_EVIDENCE_REQUIRED")
    row.status = "approved"
    row.review_json = _json({**checks, "reviewed_by_user_id": user.id, "reviewed_at": _now().isoformat()})
    row.approved_by_user_id = user.id
    row.approved_at = _now()
    row.updated_at = _now()
    prospect.status = "approved"
    prospect.updated_at = _now()
    _audit(db, ctx, user, "prospecting.proposal_approved", "website_proposal", row.id, request_id, {"prospect_id": prospect.id, "checks": {key: value for key, value in checks.items() if key != "reviewer_note"}})
    db.commit()
    db.refresh(row)
    return proposal_dict(row)


def create_share(db: Session, ctx: TenantContext, user: User, proposal_id: str, expires_in_days: int, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = require_proposal(db, ctx, proposal_id)
    if row.status != "approved":
        raise ProspectingError(409, "Only approved proposals can be shared", code="PROPOSAL_NOT_APPROVED")
    token = secrets.token_urlsafe(32)
    row.share_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row.share_expires_at = _now() + timedelta(days=expires_in_days)
    _audit(db, ctx, user, "prospecting.share_created", "website_proposal", row.id, request_id, {"expires_at": row.share_expires_at.isoformat()})
    db.commit()
    return {"proposal_id": row.id, "token": token, "public_path": f"/api/v1/public/prospecting/proposals/{token}", "expires_at": row.share_expires_at}


def public_proposal(db: Session, token: str) -> tuple[WebsiteProposal, WebsiteProspect, WebsiteAnalysis]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = db.query(WebsiteProposal).filter(WebsiteProposal.share_token_hash == token_hash, WebsiteProposal.status == "approved").first()
    if row is None or row.share_expires_at is None or row.share_expires_at < _now():
        raise ProspectingError(404, "Shared proposal not found or expired", code="SHARE_NOT_FOUND")
    prospect = db.query(WebsiteProspect).filter(WebsiteProspect.id == row.prospect_id, WebsiteProspect.tenant_id == row.tenant_id).first()
    analysis = db.query(WebsiteAnalysis).filter(WebsiteAnalysis.id == row.analysis_id, WebsiteAnalysis.tenant_id == row.tenant_id).first()
    if prospect is None or analysis is None:
        raise ProspectingError(404, "Shared proposal is incomplete", code="SHARE_INCOMPLETE")
    return row, prospect, analysis


def render_proposal_html(row: WebsiteProposal, prospect: WebsiteProspect, analysis: WebsiteAnalysis) -> str:
    proposal = proposal_dict(row)
    findings = _load(analysis.findings_json, [])
    packages = proposal["packages"]
    finding_html = "".join(f"<article><strong>{escape(str(item.get('title', 'Observation')))}</strong><p>{escape(str(item.get('detail', '')))}</p><small>Säkerhet: {round(float(item.get('confidence', 0)) * 100)}%</small></article>" for item in findings[:6])
    package_html = "".join(f"<article><h3>{escape(str(item.get('name', 'Paket')))}</h3><b>{int(item.get('price_sek', 0)):,} SEK</b><ul>{''.join(f'<li>{escape(str(feature))}</li>' for feature in item.get('features', []))}</ul></article>" for item in packages)
    sitemap = "".join(f"<span>{escape(str(page))}</span>" for page in proposal["sitemap"])
    return f"""<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(row.headline)}</title><style>
@page{{size:A4;margin:14mm}}*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f9;color:#17283e;font:15px/1.6 Inter,Arial,sans-serif}}main{{max-width:960px;margin:0 auto;background:#fff;padding:48px}}header{{padding:44px;border-radius:18px;color:#fff;background:linear-gradient(135deg,#112743,#2867d8)}}header small{{letter-spacing:.13em}}h1{{font-size:38px;line-height:1.1}}h2{{margin-top:36px}}.score{{display:inline-flex;padding:8px 14px;border-radius:30px;background:#eaf2fe;color:#245cae;font-weight:700}}.findings,.packages{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}article{{border:1px solid #e3e8ef;border-radius:12px;padding:18px}}article p,article small{{color:#69788d}}.sitemap{{display:flex;flex-wrap:wrap;gap:8px}}.sitemap span{{padding:8px 12px;border-radius:8px;background:#f1f5fa}}footer{{margin-top:40px;padding-top:20px;border-top:1px solid #e3e8ef;color:#718096}}@media(max-width:700px){{main{{padding:20px}}.findings,.packages{{grid-template-columns:1fr}}h1{{font-size:28px}}}}@media print{{body{{background:#fff}}main{{padding:0}}}}
</style></head><body><main><header><small>KUNDANPASSAT WEBBFÖRSLAG</small><h1>{escape(row.headline)}</h1><p>{escape(row.summary)}</p></header><h2>Analys av nuläget</h2><p class="score">Förbättringspotential {analysis.improvement_score}/100</p><div class="findings">{finding_html}</div><h2>Föreslagen webbstruktur</h2><div class="sitemap">{sitemap}</div><h2>Tre genomförandenivåer</h2><div class="packages">{package_html}</div><footer>Förslag version {row.version} · {escape(prospect.company_name)} · Giltigt till {row.share_expires_at.date().isoformat() if row.share_expires_at else '—'}<br>Utskrift: använd webbläsarens Skriv ut → Spara som PDF.</footer></main></body></html>"""


def deliver_proposal(db: Session, ctx: TenantContext, user: User, proposal_id: str, payload: DeliveryRequest, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    row = require_proposal(db, ctx, proposal_id)
    prospect = require_prospect(db, ctx, row.prospect_id)
    if row.status != "approved" or row.approved_by_user_id is None:
        raise ProspectingError(409, "Human approval is required before delivery", code="PROPOSAL_NOT_APPROVED")
    recipient = (payload.test_recipient or prospect.contact_email or "").strip().lower()
    if not recipient or "@" not in recipient:
        raise ProspectingError(409, "A valid recipient is required", code="RECIPIENT_REQUIRED")
    is_test = payload.test_recipient is not None
    if is_test and recipient != user.email.strip().lower():
        raise ProspectingError(403, "Test delivery may only be sent to the authenticated operator", code="TEST_RECIPIENT_FORBIDDEN")
    if not is_test:
        if not prospect.contact_verified:
            raise ProspectingError(409, "The recipient contact is not verified", code="CONTACT_NOT_VERIFIED")
        if prospect.do_not_contact or _is_suppressed(db, ctx.tenant_id, recipient):
            raise ProspectingError(409, "The contact is on the suppression list", code="CONTACT_SUPPRESSED")
        if row.delivery_status in {"queued", "mock_delivered", "delivered"}:
            raise ProspectingError(409, "This approved proposal has already been processed for delivery", code="DELIVERY_ALREADY_PROCESSED")
        policy = db.query(ProspectingPolicy).filter(ProspectingPolicy.tenant_id == ctx.tenant_id).first()
        daily_limit = policy.daily_delivery_limit if policy else 20
        if prospect.campaign_id:
            campaign = _require_campaign(db, ctx, prospect.campaign_id)
            daily_limit = campaign.daily_limit
        today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        processed_today = db.query(WebsiteProposal).filter(
            WebsiteProposal.tenant_id == ctx.tenant_id,
            WebsiteProposal.delivery_status.in_(["queued", "mock_delivered", "delivered"]),
            WebsiteProposal.updated_at >= today,
        ).count()
        if processed_today >= daily_limit:
            raise ProspectingError(429, "The tenant delivery limit for today has been reached", code="DELIVERY_DAILY_LIMIT")
    token = opt_out_token(ctx.tenant_id, prospect.id, recipient)
    opt_out_url = f"{settings.PROSPECTING_PUBLIC_BASE_URL.rstrip('/')}/api/v1/public/prospecting/opt-out/{prospect.id}/{token}"
    share_url = None
    if payload.share_token:
        presented_hash = hashlib.sha256(payload.share_token.encode("utf-8")).hexdigest()
        if not row.share_token_hash or not secrets.compare_digest(row.share_token_hash, presented_hash):
            raise ProspectingError(422, "The proposal share token is invalid", code="SHARE_TOKEN_INVALID")
        if row.share_expires_at is None or row.share_expires_at < _now():
            raise ProspectingError(409, "The proposal share link has expired", code="SHARE_TOKEN_EXPIRED")
        share_url = f"{settings.PROSPECTING_PUBLIC_BASE_URL.rstrip('/')}/api/v1/public/prospecting/proposals/{payload.share_token}"
    text_body = f"{row.email_body}\n\n{('Se det personliga förslaget: ' + share_url) if share_url else ''}\n\nVill du inte ha fler meddelanden: {opt_out_url}".strip()
    share_html = f"<p><a href='{escape(share_url)}'>Se ditt personliga webbförslag</a></p>" if share_url else ""
    html_body = "<div style='font-family:Arial,sans-serif;white-space:pre-line'>" + escape(row.email_body) + f"</div>{share_html}<p><a href='{escape(opt_out_url)}'>Avregistrera</a></p>"
    try:
        recipient_fingerprint = hashlib.sha256(recipient.encode("utf-8")).hexdigest()[:16]
        receipt = deliver_email(
            provider=payload.provider,
            recipient=recipient,
            subject=row.email_subject,
            text_body=text_body,
            html_body=html_body,
            unsubscribe_url=opt_out_url,
            idempotency_key=f"prospecting-{ctx.tenant_id}-{row.id}-{recipient_fingerprint}",
        )
    except ProspectingDeliveryError as exc:
        row.delivery_status = "failed"
        row.delivery_provider = payload.provider
        db.commit()
        raise ProspectingError(exc.status_code, exc.detail, code=exc.code) from exc
    row.delivery_status = "delivered" if receipt.external_sent else "queued" if payload.provider == "queue" else "mock_delivered"
    row.delivery_provider = receipt.provider
    row.delivery_id = receipt.delivery_id
    row.delivered_at = _now() if receipt.external_sent else None
    row.updated_at = _now()
    _audit(db, ctx, user, "prospecting.delivery_processed", "website_proposal", row.id, request_id, {"provider": receipt.provider, "external_sent": receipt.external_sent, "recipient_domain": recipient.split("@")[-1], "test": is_test})
    db.commit()
    return {
        "proposal_id": row.id,
        "status": row.delivery_status,
        "provider": receipt.provider,
        "delivery_id": receipt.delivery_id,
        "external_sent": receipt.external_sent,
        "recipient": recipient,
        "phase_disclaimer": "Delivery is approval-gated, suppression-aware, audited, and fail-closed. Queue/mock never send externally.",
    }


def _upsert_suppression(db: Session, tenant_id: int, email: str, reason: str, source: str, prospect_id: str | None, user_id: int | None) -> ProspectSuppression:
    normalized = email.strip().lower()
    row = db.query(ProspectSuppression).filter(ProspectSuppression.tenant_id == tenant_id, ProspectSuppression.normalized_email == normalized).first()
    if row:
        row.reason = reason
        row.source = source
        return row
    row = ProspectSuppression(id=new_suppression_id(), tenant_id=tenant_id, prospect_id=prospect_id, normalized_email=normalized, reason=reason, source=source, created_by_user_id=user_id)
    db.add(row)
    return row


def add_suppression(db: Session, ctx: TenantContext, user: User, payload: SuppressionCreate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    email = payload.email.strip().lower()
    if "@" not in email:
        raise ProspectingError(422, "A valid email is required", code="EMAIL_INVALID")
    if payload.prospect_id:
        require_prospect(db, ctx, payload.prospect_id)
    row = _upsert_suppression(db, ctx.tenant_id, email, payload.reason, "operator", payload.prospect_id, user.id)
    if payload.prospect_id:
        prospect = require_prospect(db, ctx, payload.prospect_id)
        prospect.do_not_contact = True
        prospect.updated_at = _now()
    _audit(db, ctx, user, "prospecting.contact_suppressed", "prospect_suppression", row.id, request_id, {"reason": payload.reason})
    db.commit()
    return {"id": row.id, "email": row.normalized_email, "reason": row.reason, "source": row.source, "created_at": row.created_at}


def public_opt_out(db: Session, prospect_id: str, token: str) -> dict:
    prospect = db.query(WebsiteProspect).filter(WebsiteProspect.id == prospect_id).first()
    if prospect is None or not prospect.contact_email or not verify_opt_out_token(token, prospect.tenant_id, prospect.id, prospect.contact_email):
        raise ProspectingError(404, "Opt-out link is invalid", code="OPT_OUT_INVALID")
    row = _upsert_suppression(db, prospect.tenant_id, prospect.contact_email, "opt_out", "public_opt_out", prospect.id, None)
    prospect.do_not_contact = True
    prospect.updated_at = _now()
    db.commit()
    return {"status": "suppressed", "message": "Adressen kommer inte att få fler prospekteringsutskick.", "reference": row.id}


def discover_for_campaign(db: Session, ctx: TenantContext, user: User, campaign_id: str, query: str, region: str | None, limit: int, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    campaign = _require_campaign(db, ctx, campaign_id)
    try:
        companies = discover_companies(query, region or campaign.region, min(limit, campaign.daily_limit))
    except DiscoveryProviderError as exc:
        raise ProspectingError(exc.status_code, exc.detail, code=exc.code) from exc
    created: list[dict] = []
    skipped: list[dict] = []
    for company in companies:
        if not company.website_url:
            skipped.append({"company_name": company.company_name, "reason": "website_missing", "source_url": company.source_url})
            continue
        try:
            domain = _domain(company.website_url)
        except WebsiteAuditError:
            skipped.append({"company_name": company.company_name, "reason": "website_invalid", "source_url": company.source_url})
            continue
        duplicate = db.query(WebsiteProspect).filter(WebsiteProspect.tenant_id == ctx.tenant_id, WebsiteProspect.normalized_domain == domain).first()
        if duplicate:
            skipped.append({"company_name": company.company_name, "reason": "duplicate_domain", "prospect_id": duplicate.id})
            continue
        row = WebsiteProspect(
            id=new_prospect_id(), tenant_id=ctx.tenant_id, campaign_id=campaign.id, assigned_user_id=user.id,
            company_name=company.company_name, website_url=normalize_public_url(company.website_url), normalized_domain=domain,
            industry=company.industry or campaign.industry, city=company.city, qualification_score=campaign.min_score,
            estimated_value_sek=0, status="qualified", legal_basis="legitimate_interest_b2b",
            legitimate_interest_note="Public business listing; relevance and contact basis must be verified before outreach.",
            retention_until=_now() + timedelta(days=180), source_provider="google_places", source_url=company.source_url, source_checked_at=_now(),
        )
        db.add(row)
        db.flush()
        created.append(prospect_dict(db, row, include_latest=False))
    _audit(db, ctx, user, "prospecting.discovery_completed", "prospecting_campaign", campaign.id, request_id, {"created": len(created), "skipped": len(skipped), "provider": settings.PROSPECTING_DISCOVERY_PROVIDER})
    db.commit()
    return {"created": created, "skipped": skipped, "provider": settings.PROSPECTING_DISCOVERY_PROVIDER}


def policy_dict(row: ProspectingPolicy | None, ctx: TenantContext) -> dict:
    return {
        "tenant_id": ctx.tenant_id,
        "mode": row.mode if row else "manual_review",
        "auto_analyze": row.auto_analyze if row else False,
        "auto_generate_proposal": row.auto_generate_proposal if row else False,
        "auto_queue_after_approval": row.auto_queue_after_approval if row else False,
        "minimum_score": row.minimum_score if row else 80,
        "daily_delivery_limit": row.daily_delivery_limit if row else 20,
        "real_email_enabled": settings.PROSPECTING_REAL_EMAIL_ENABLED,
        "scheduler_enabled": settings.AGENT_SCHEDULER_ENABLED,
        "updated_at": row.updated_at if row else None,
    }


def get_policy(db: Session, ctx: TenantContext) -> dict:
    row = db.query(ProspectingPolicy).filter(ProspectingPolicy.tenant_id == ctx.tenant_id).first()
    return policy_dict(row, ctx)


def update_policy(db: Session, ctx: TenantContext, user: User, payload: ProspectingPolicyUpdate, *, request_id: str | None = None) -> dict:
    _require_write(ctx)
    if payload.mode == "rules_assisted" and not settings.AGENT_SCHEDULER_ENABLED:
        # Rules may still be persisted and previewed, but background execution stays visibly off.
        scheduler_warning = True
    else:
        scheduler_warning = False
    row = db.query(ProspectingPolicy).filter(ProspectingPolicy.tenant_id == ctx.tenant_id).first()
    if row is None:
        row = ProspectingPolicy(tenant_id=ctx.tenant_id, updated_by_user_id=user.id)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by_user_id = user.id
    row.updated_at = _now()
    _audit(db, ctx, user, "prospecting.policy_updated", "prospecting_policy", str(ctx.tenant_id), request_id, {**payload.model_dump(), "scheduler_warning": scheduler_warning, "real_email_enabled": settings.PROSPECTING_REAL_EMAIL_ENABLED})
    db.commit()
    db.refresh(row)
    return policy_dict(row, ctx)


def summary(db: Session, ctx: TenantContext) -> dict:
    prospects = db.query(WebsiteProspect).filter(WebsiteProspect.tenant_id == ctx.tenant_id).all()
    analyzed_sites = db.query(WebsiteAnalysis).filter(WebsiteAnalysis.tenant_id == ctx.tenant_id, WebsiteAnalysis.status == "complete").count()
    awaiting = db.query(WebsiteProposal).filter(WebsiteProposal.tenant_id == ctx.tenant_id, WebsiteProposal.status == "draft").count()
    approved = db.query(WebsiteProposal).filter(WebsiteProposal.tenant_id == ctx.tenant_id, WebsiteProposal.status == "approved").count()
    suppressed = db.query(ProspectSuppression).filter(ProspectSuppression.tenant_id == ctx.tenant_id).count()
    return {
        "analyzed_sites": analyzed_sites,
        "qualified_opportunities": len([row for row in prospects if row.status not in {"lost", "won"}]),
        "awaiting_review": awaiting,
        "approved": approved,
        "potential_value_sek": sum(row.estimated_value_sek for row in prospects if row.status != "lost"),
        "suppressed_contacts": suppressed,
        "providers": provider_status(),
    }
