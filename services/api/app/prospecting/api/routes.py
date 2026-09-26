"""Authenticated website prospecting API plus tokenized public proposal/opt-out routes.

Transport only: every handler resolves a tenant context, optionally spends a
rate-limit token, and delegates to the service layer. Domain failures raise
``ProspectingError`` and are rendered by the application-wide handler in
``app.core.errors``, so there is exactly one error contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import PlatformPrincipal, get_platform_principal, get_tenant_context
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.prospecting.presentation import render_meeting_presentation_html
from app.prospecting.schemas import (
    AnalysisItem,
    AnalysisRequest,
    CampaignCreate,
    CampaignItem,
    DeliveryRequest,
    DeliveryResult,
    DiscoveryRequest,
    ProposalCreate,
    ProposalItem,
    ProposalReview,
    ProposalUpdate,
    ProspectBulkCsvRequest,
    ProspectBulkCsvResult,
    ProspectCreate,
    ProspectingPolicyItem,
    ProspectingPolicyUpdate,
    ProspectingSummary,
    ProspectItem,
    ProspectPromoteRequest,
    ProspectPromoteResult,
    ProspectUpdate,
    ShareCreate,
    ShareCreated,
    SuppressionCreate,
)
from app.prospecting.service import (
    add_suppression,
    approve_proposal,
    bulk_create_prospects_from_csv,
    create_campaign,
    create_prospect,
    create_share,
    deliver_proposal,
    discover_for_campaign,
    generate_proposal,
    get_policy,
    list_analyses,
    list_campaigns,
    list_proposals,
    list_prospects,
    promote_prospect_to_crm,
    proposal_dict,
    prospect_dict,
    public_opt_out,
    public_proposal,
    render_proposal_html,
    require_analysis_for_proposal,
    require_proposal,
    require_prospect,
    run_analysis,
    summary,
    update_policy,
    update_proposal,
    update_prospect,
)
from app.tenancy.service import TenantContext

router = APIRouter(prefix="/prospecting", tags=["website-prospecting"])
public_router = APIRouter(prefix="/public/prospecting", tags=["public-website-proposals"])

HTML_SECURITY_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def get_prospecting_context(
    tenant_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Tenant comes from the signed token; an explicit ?tenant_id may only agree."""
    if tenant_id is not None and tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    return ctx


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _paginate(response: Response, page) -> list[dict]:
    """Expose paging state in headers so the list body stays a plain array."""
    response.headers["X-Total-Count"] = str(page.total)
    response.headers["X-Has-More"] = "true" if page.has_more else "false"
    return page.items


def _html_response(html: str, csp: str) -> Response:
    return Response(
        content=html,
        media_type="text/html",
        headers={**HTML_SECURITY_HEADERS, "Content-Security-Policy": csp},
    )


def _presentation_response(html: str) -> Response:
    return _html_response(
        html,
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "img-src data:; connect-src 'none'; media-src 'none'; font-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    )


@router.get("/summary", response_model=ProspectingSummary)
def get_summary(
    db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)
) -> ProspectingSummary:
    return ProspectingSummary(**summary(db, ctx))


@router.get("/policy", response_model=ProspectingPolicyItem)
def get_prospecting_policy(
    db: Session = Depends(get_db), ctx: TenantContext = Depends(get_prospecting_context)
) -> ProspectingPolicyItem:
    return ProspectingPolicyItem(**get_policy(db, ctx))


@router.patch("/policy", response_model=ProspectingPolicyItem)
def patch_prospecting_policy(
    payload: ProspectingPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectingPolicyItem:
    return ProspectingPolicyItem(
        **update_policy(db, ctx, principal, payload, request_id=_request_id(request))
    )


@router.get("/campaigns", response_model=list[CampaignItem])
def get_campaigns(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> list[CampaignItem]:
    page = list_campaigns(db, ctx, limit=limit, offset=offset)
    return [CampaignItem(**item) for item in _paginate(response, page)]


@router.post("/campaigns", response_model=CampaignItem, status_code=status.HTTP_201_CREATED)
def post_campaign(
    payload: CampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> CampaignItem:
    return CampaignItem(**create_campaign(db, ctx, principal, payload, request_id=_request_id(request)))


@router.post("/campaigns/{campaign_id}/discover")
def post_discover(
    campaign_id: str,
    payload: DiscoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> dict:
    limiter.check(
        "discovery", ctx.tenant_id, settings.PROSPECTING_DISCOVERY_RATE_LIMIT_PER_MINUTE
    )
    return discover_for_campaign(
        db,
        ctx,
        principal,
        campaign_id,
        payload.query,
        payload.region,
        payload.limit,
        request_id=_request_id(request),
    )


@router.get("/prospects", response_model=list[ProspectItem])
def get_prospects(
    response: Response,
    prospect_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> list[ProspectItem]:
    page = list_prospects(db, ctx, status=prospect_status, search=search, limit=limit, offset=offset)
    return [ProspectItem(**item) for item in _paginate(response, page)]


@router.post("/prospects", response_model=ProspectItem, status_code=status.HTTP_201_CREATED)
def post_prospect(
    payload: ProspectCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectItem:
    return ProspectItem(**create_prospect(db, ctx, principal, payload, request_id=_request_id(request)))


@router.post("/prospects/bulk-csv", response_model=ProspectBulkCsvResult)
def post_prospects_bulk_csv(
    payload: ProspectBulkCsvRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectBulkCsvResult:
    """N1-3: CSV paste intake (<=50 rows). Skips duplicates; never applies contact email from CSV."""
    return ProspectBulkCsvResult(
        **bulk_create_prospects_from_csv(db, ctx, principal, payload, request_id=_request_id(request))
    )


@router.get("/prospects/{prospect_id}", response_model=ProspectItem)
def get_prospect(
    prospect_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> ProspectItem:
    return ProspectItem(**prospect_dict(db, require_prospect(db, ctx, prospect_id)))


@router.post("/prospects/{prospect_id}/promote", response_model=ProspectPromoteResult)
def post_promote_prospect(
    prospect_id: str,
    payload: ProspectPromoteRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectPromoteResult:
    """N1-1: hand off Nova prospect -> CRM customer + lead + case (no outbound)."""
    return ProspectPromoteResult(
        **promote_prospect_to_crm(db, ctx, principal, prospect_id, payload, request_id=_request_id(request))
    )


@router.patch("/prospects/{prospect_id}", response_model=ProspectItem)
def patch_prospect(
    prospect_id: str,
    payload: ProspectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProspectItem:
    return ProspectItem(
        **update_prospect(db, ctx, principal, prospect_id, payload, request_id=_request_id(request))
    )


@router.post(
    "/prospects/{prospect_id}/analyses",
    response_model=AnalysisItem,
    status_code=status.HTTP_201_CREATED,
)
def post_analysis(
    prospect_id: str,
    payload: AnalysisRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> AnalysisItem:
    limiter.check("analysis", ctx.tenant_id, settings.PROSPECTING_ANALYSIS_RATE_LIMIT_PER_MINUTE)
    return AnalysisItem(
        **run_analysis(db, ctx, principal, prospect_id, payload, request_id=_request_id(request))
    )


@router.get("/prospects/{prospect_id}/analyses", response_model=list[AnalysisItem])
def get_analyses(
    prospect_id: str,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> list[AnalysisItem]:
    page = list_analyses(db, ctx, prospect_id, limit=limit, offset=offset)
    return [AnalysisItem(**item) for item in _paginate(response, page)]


@router.post(
    "/prospects/{prospect_id}/proposals",
    response_model=ProposalItem,
    status_code=status.HTTP_201_CREATED,
)
def post_proposal(
    prospect_id: str,
    payload: ProposalCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    return ProposalItem(
        **generate_proposal(
            db, ctx, principal, prospect_id, payload.analysis_id, request_id=_request_id(request)
        )
    )


@router.get("/prospects/{prospect_id}/proposals", response_model=list[ProposalItem])
def get_proposals(
    prospect_id: str,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> list[ProposalItem]:
    page = list_proposals(db, ctx, prospect_id, limit=limit, offset=offset)
    return [ProposalItem(**item) for item in _paginate(response, page)]


@router.get("/proposals/{proposal_id}", response_model=ProposalItem)
def get_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> ProposalItem:
    return ProposalItem(**proposal_dict(require_proposal(db, ctx, proposal_id)))


@router.get("/proposals/{proposal_id}/presentation")
def get_proposal_presentation(
    proposal_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
) -> Response:
    """Preview the self-running meeting film without creating a public share."""
    proposal = require_proposal(db, ctx, proposal_id)
    prospect = require_prospect(db, ctx, proposal.prospect_id)
    analysis = require_analysis_for_proposal(db, ctx, proposal, prospect)
    return _presentation_response(render_meeting_presentation_html(proposal, prospect, analysis))


@router.patch("/proposals/{proposal_id}", response_model=ProposalItem)
def patch_proposal(
    proposal_id: str,
    payload: ProposalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    return ProposalItem(
        **update_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request))
    )


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalItem)
def post_approve(
    proposal_id: str,
    payload: ProposalReview,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ProposalItem:
    return ProposalItem(
        **approve_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request))
    )


@router.post("/proposals/{proposal_id}/share", response_model=ShareCreated)
def post_share(
    proposal_id: str,
    payload: ShareCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> ShareCreated:
    return ShareCreated(
        **create_share(
            db, ctx, principal, proposal_id, payload.expires_in_days, request_id=_request_id(request)
        )
    )


@router.post("/proposals/{proposal_id}/deliver", response_model=DeliveryResult)
def post_deliver(
    proposal_id: str,
    payload: DeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> DeliveryResult:
    limiter.check("delivery", ctx.tenant_id, settings.PROSPECTING_DELIVERY_RATE_LIMIT_PER_MINUTE)
    return DeliveryResult(
        **deliver_proposal(db, ctx, principal, proposal_id, payload, request_id=_request_id(request))
    )


@router.post("/suppressions", status_code=status.HTTP_201_CREATED)
def post_suppression(
    payload: SuppressionCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_prospecting_context),
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> dict:
    return add_suppression(db, ctx, principal, payload, request_id=_request_id(request))


@public_router.get("/proposals/{token}")
def get_public_proposal(token: str, db: Session = Depends(get_db)) -> Response:
    proposal, prospect, analysis = public_proposal(db, token)
    html = render_proposal_html(
        proposal,
        prospect,
        analysis,
        presentation_path=f"/api/v1/public/prospecting/presentations/{token}",
    )
    return _html_response(
        html,
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    )


@public_router.get("/presentations/{token}")
def get_public_presentation(token: str, db: Session = Depends(get_db)) -> Response:
    """Play the approved proposal as a self-running, no-network meeting film."""
    proposal, prospect, analysis = public_proposal(db, token)
    return _presentation_response(render_meeting_presentation_html(proposal, prospect, analysis))


@public_router.post("/opt-out/{prospect_id}/{token}")
def post_public_opt_out(prospect_id: str, token: str, db: Session = Depends(get_db)) -> dict:
    return public_opt_out(db, prospect_id, token)
