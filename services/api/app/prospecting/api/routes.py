"""Authenticated website prospecting API plus tokenized public proposal/opt-out routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.prospecting.models import WebsiteAnalysis, WebsiteProposal
from app.prospecting.presentation import render_meeting_presentation_html
from app.prospecting.schemas import (
    AnalysisItem,
    AnalysisRequest,
    CampaignCreate,
    CampaignItem,
    DeliveryRequest,
    DeliveryResult,
    DiscoveryRequest,
    ProspectBulkCsvRequest,
    ProspectBulkCsvResult,
    ProspectCreate,
    ProspectItem,
    ProspectPromoteRequest,
    ProspectPromoteResult,
    ProspectUpdate,
    ProspectingPolicyItem,
    ProspectingPolicyUpdate,
    ProspectingSummary,
    ProposalCreate,
    ProposalItem,
    ProposalReview,
    ProposalUpdate,
    ShareCreate,
    ShareCreated,
    SuppressionCreate,
)
from app.prospecting.service import (
    ProspectingError,
    add_suppression,
    analysis_dict,
    approve_proposal,
    bulk_create_prospects_from_csv,
    campaign_dict,
    create_campaign,
    create_prospect,
    create_share,
    deliver_proposal,
    discover_for_campaign,
    generate_proposal,
    get_policy,
    list_campaigns,
    list_prospects,
    promote_prospect_to_crm,
    proposal_dict,
    prospect_dict,
    public_opt_out,
    public_proposal,
    render_proposal_html,
    require_proposal,
    require_prospect,
    run_analysis,
    summary,
    update_policy,
    update_proposal,
    update_prospect,
)
from app.auth import PlatformPrincipal, get_platform_principal, get_tenant_context
from app.tenancy.service import TenantContext

router = APIRouter(prefix="/prospecting", tags=["website-prospecting"])
public_router = APIRouter(prefix="/public/prospecting", tags=["public-website-proposals"])


def get_prospecting_context(
    tenant_id: Optional[str] = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    if tenant_id is not None and tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    return ctx


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or getattr(request.state, "request_id", None)


def _http_error(exc: ProspectingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"message": exc.detail, "code": exc.code})


def _meeting_presentation_response(html: str) -> Response:
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "img-src data:; connect-src 'none'; media-src 'none'; font-src 'none'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/summary", response_model=ProspectingSummary)
def get_summary(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> ProspectingSummary:
    return ProspectingSummary(**summary(db, ctx))


@router.get("/policy", response_model=ProspectingPolicyItem)
def get_prospecting_policy(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> ProspectingPolicyItem:
    return ProspectingPolicyItem(**get_policy(db, ctx))


@router.patch("/policy", response_model=ProspectingPolicyItem)
def patch_prospecting_policy(
    payload: ProspectingPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectingPolicyItem:
    try:
        return ProspectingPolicyItem(**update_policy(db, ctx, principal, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/campaigns", response_model=list[CampaignItem])
def get_campaigns(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> list[CampaignItem]:
    return [CampaignItem(**item) for item in list_campaigns(db, ctx)]


@router.post("/campaigns", response_model=CampaignItem, status_code=status.HTTP_201_CREATED)
def post_campaign(
    payload: CampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> CampaignItem:
    try:
        return CampaignItem(**create_campaign(db, ctx, principal, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/campaigns/{campaign_id}/discover")
def post_discover(
    campaign_id: str,
    payload: DiscoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> dict:
    try:
        return discover_for_campaign(db, ctx, principal, campaign_id, payload.query, payload.region, payload.limit, request_id=_request_id(request))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/prospects", response_model=list[ProspectItem])
def get_prospects(
    prospect_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> list[ProspectItem]:
    return [ProspectItem(**item) for item in list_prospects(db, ctx, status=prospect_status, search=search, limit=limit)]


@router.post("/prospects", response_model=ProspectItem, status_code=status.HTTP_201_CREATED)
def post_prospect(
    payload: ProspectCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectItem:
    try:
        return ProspectItem(**create_prospect(db, ctx, principal, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/prospects/bulk-csv", response_model=ProspectBulkCsvResult)
def post_prospects_bulk_csv(
    payload: ProspectBulkCsvRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectBulkCsvResult:
    """N1-3: CSV paste intake (≤50 rows). Skips duplicates; never applies contact email from CSV."""
    try:
        return ProspectBulkCsvResult(**bulk_create_prospects_from_csv(db, ctx, principal, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/prospects/{prospect_id}", response_model=ProspectItem)
def get_prospect(prospect_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> ProspectItem:
    try:
        return ProspectItem(**prospect_dict(db, require_prospect(db, ctx, prospect_id)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/prospects/{prospect_id}/promote", response_model=ProspectPromoteResult)
def post_promote_prospect(
    prospect_id: str,
    payload: ProspectPromoteRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectPromoteResult:
    """N1-1: hand off Nova prospect → CRM customer + lead + case (no outbound)."""
    try:
        return ProspectPromoteResult(
            **promote_prospect_to_crm(db, ctx, principal, prospect_id, payload, request_id=_request_id(request))
        )
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.patch("/prospects/{prospect_id}", response_model=ProspectItem)
def patch_prospect(
    prospect_id: str,
    payload: ProspectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectItem:
    try:
        return ProspectItem(**update_prospect(db, ctx, principal, prospect_id, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/prospects/{prospect_id}/analyses", response_model=AnalysisItem, status_code=status.HTTP_201_CREATED)
def post_analysis(
    prospect_id: str,
    payload: AnalysisRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> AnalysisItem:
    try:
        return AnalysisItem(**run_analysis(db, ctx, principal, prospect_id, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/prospects/{prospect_id}/analyses", response_model=list[AnalysisItem])
def get_analyses(prospect_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> list[AnalysisItem]:
    try:
        require_prospect(db, ctx, prospect_id)
    except ProspectingError as exc:
        raise _http_error(exc) from exc
    rows = db.query(WebsiteAnalysis).filter(WebsiteAnalysis.tenant_id == ctx.tenant_id, WebsiteAnalysis.prospect_id == prospect_id).order_by(WebsiteAnalysis.created_at.desc()).all()
    return [AnalysisItem(**analysis_dict(row)) for row in rows]


@router.post("/prospects/{prospect_id}/proposals", response_model=ProposalItem, status_code=status.HTTP_201_CREATED)
def post_proposal(
    prospect_id: str,
    payload: ProposalCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    try:
        return ProposalItem(**generate_proposal(db, ctx, principal, prospect_id, payload.analysis_id, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/prospects/{prospect_id}/proposals", response_model=list[ProposalItem])
def get_proposals(prospect_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> list[ProposalItem]:
    try:
        require_prospect(db, ctx, prospect_id)
    except ProspectingError as exc:
        raise _http_error(exc) from exc
    rows = db.query(WebsiteProposal).filter(WebsiteProposal.tenant_id == ctx.tenant_id, WebsiteProposal.prospect_id == prospect_id).order_by(WebsiteProposal.version.desc()).all()
    return [ProposalItem(**proposal_dict(row)) for row in rows]


@router.get("/proposals/{proposal_id}", response_model=ProposalItem)
def get_proposal(proposal_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)) -> ProposalItem:
    try:
        return ProposalItem(**proposal_dict(require_proposal(db, ctx, proposal_id)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.get("/proposals/{proposal_id}/presentation")
def get_proposal_presentation(
    proposal_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> Response:
    """Preview the self-running meeting film without creating a public share."""
    try:
        proposal = require_proposal(db, ctx, proposal_id)
        prospect = require_prospect(db, ctx, proposal.prospect_id)
        analysis = (
            db.query(WebsiteAnalysis)
            .filter(
                WebsiteAnalysis.tenant_id == ctx.tenant_id,
                WebsiteAnalysis.id == proposal.analysis_id,
                WebsiteAnalysis.prospect_id == prospect.id,
                WebsiteAnalysis.status == "complete",
            )
            .first()
        )
        if analysis is None:
            raise ProspectingError(
                409,
                "A completed analysis is required for the meeting presentation",
                code="PRESENTATION_ANALYSIS_REQUIRED",
            )
        html = render_meeting_presentation_html(proposal, prospect, analysis)
    except ProspectingError as exc:
        raise _http_error(exc) from exc
    return _meeting_presentation_response(html)


@router.patch("/proposals/{proposal_id}", response_model=ProposalItem)
def patch_proposal(
    proposal_id: str,
    payload: ProposalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    try:
        return ProposalItem(**update_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalItem)
def post_approve(
    proposal_id: str,
    payload: ProposalReview,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    try:
        return ProposalItem(**approve_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/proposals/{proposal_id}/share", response_model=ShareCreated)
def post_share(
    proposal_id: str,
    payload: ShareCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ShareCreated:
    try:
        return ShareCreated(**create_share(db, ctx, principal, proposal_id, payload.expires_in_days, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/proposals/{proposal_id}/deliver", response_model=DeliveryResult)
def post_deliver(
    proposal_id: str,
    payload: DeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> DeliveryResult:
    try:
        return DeliveryResult(**deliver_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request)))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@router.post("/suppressions", status_code=status.HTTP_201_CREATED)
def post_suppression(
    payload: SuppressionCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> dict:
    try:
        return add_suppression(db, ctx, principal, payload, request_id=_request_id(request))
    except ProspectingError as exc:
        raise _http_error(exc) from exc


@public_router.get("/proposals/{token}")
def get_public_proposal(token: str, db: Session = Depends(get_db)) -> Response:
    try:
        proposal, prospect, analysis = public_proposal(db, token)
        html = render_proposal_html(
            proposal,
            prospect,
            analysis,
            presentation_path=f"/api/v1/public/prospecting/presentations/{token}",
        )
    except ProspectingError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
        },
    )


@public_router.get("/presentations/{token}")
def get_public_presentation(token: str, db: Session = Depends(get_db)) -> Response:
    """Play the approved proposal as a self-running, no-network meeting film."""
    try:
        proposal, prospect, analysis = public_proposal(db, token)
        html = render_meeting_presentation_html(proposal, prospect, analysis)
    except ProspectingError as exc:
        raise _http_error(exc) from exc
    return _meeting_presentation_response(html)


@public_router.post("/opt-out/{prospect_id}/{token}")
def post_public_opt_out(prospect_id: str, token: str, db: Session = Depends(get_db)) -> dict:
    try:
        return public_opt_out(db, prospect_id, token)
    except ProspectingError as exc:
        raise _http_error(exc) from exc
