from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import main so all relationship targets and metadata tables are registered.
from app.main import _safe_log_path, app as _app  # noqa: F401
from app.db.session import Base
from app.models.tenancy import Tenant
from app.models.user import User
from app.prospecting.analyzer import WebsiteAuditError, analyze_html, normalize_public_url
from app.prospecting.outbound import deliver_email, opt_out_token
from app.prospecting.pagespeed import PageSpeedError, run_pagespeed
from app.prospecting.schemas import (
    AnalysisRequest,
    CampaignCreate,
    DeliveryRequest,
    ProspectCreate,
    ProspectingPolicyUpdate,
    ProposalReview,
)
from app.prospecting.service import (
    ProspectingError,
    approve_proposal,
    create_campaign,
    create_prospect,
    create_share,
    deliver_proposal,
    generate_proposal,
    get_policy,
    public_opt_out,
    public_proposal,
    render_proposal_html,
    run_analysis,
    update_policy,
)
from app.tenancy.service import TenantContext


HTML = """<!doctype html>
<html lang="sv"><head><title>Exempel Bygg AB</title><meta name="viewport" content="width=device-width">
</head><body><h1>Vi bygger i Göteborg</h1><img src="hero.jpg"><p>Kontakta oss för offert.</p>
<form><input name="name"><input name="email"><button>Skicka</button></form></body></html>"""


def _db_and_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(email="prospecting-admin@example.invalid", password_hash="x", role="admin", is_active=True)
    tenant = Tenant(slug="prospecting-test", display_name="Prospecting Test", status="active")
    db.add_all([user, tenant])
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    ctx = TenantContext(
        tenant=tenant,
        workspace=None,
        membership=None,
        role="platform_admin",
        access_scope="tenant_all_profiles",
        is_platform_admin_context=True,
    )
    return db, ctx, user


def test_prospecting_routes_are_mounted():
    paths = _app.openapi()["paths"]
    required = {
        "/api/v1/prospecting/summary",
        "/api/v1/prospecting/policy",
        "/api/v1/prospecting/prospects/{prospect_id}/analyses",
        "/api/v1/prospecting/proposals/{proposal_id}/approve",
        "/api/v1/prospecting/proposals/{proposal_id}/deliver",
        "/api/v1/public/prospecting/proposals/{token}",
        "/api/v1/public/prospecting/opt-out/{prospect_id}/{token}",
    }
    assert required <= set(paths)
    assert "security" in paths["/api/v1/prospecting/summary"]["get"]
    assert "security" not in paths["/api/v1/public/prospecting/proposals/{token}"]["get"]


def test_html_analysis_has_metrics_findings_evidence_and_limitations():
    result = analyze_html(HTML, "https://example.org/")
    assert result["improvement_score"] >= 45
    assert set(result["metrics"]) == {"performance", "seo", "accessibility", "mobile"}
    assert result["findings"]
    assert all(item["evidence_ids"] for item in result["findings"])
    assert any(item["id"] == "ev_images" for item in result["evidence"])
    assert result["technical"]["scope"] == "single_page_static_html"
    assert "Core Web Vitals require a browser/Lighthouse provider" in result["technical"]["limitations"]


def test_url_guard_rejects_local_and_credential_urls():
    for url in ("http://localhost/", "http://127.0.0.1/", "https://user:pass@example.org/"):
        try:
            normalize_public_url(url)
        except WebsiteAuditError as exc:
            assert exc.code in {"URL_HOST_BLOCKED", "URL_CREDENTIALS_BLOCKED"}
        else:
            raise AssertionError(f"Expected URL to be blocked: {url}")


def test_persistent_workflow_requires_human_review_and_honors_opt_out():
    db, ctx, user = _db_and_context()
    assert get_policy(db, ctx)["mode"] == "manual_review"
    policy = update_policy(
        db,
        ctx,
        user,
        ProspectingPolicyUpdate(
            mode="rules_assisted",
            auto_analyze=True,
            auto_generate_proposal=True,
            auto_queue_after_approval=True,
            minimum_score=82,
            daily_delivery_limit=12,
        ),
        request_id="req-policy",
    )
    assert policy["mode"] == "rules_assisted"
    assert policy["scheduler_enabled"] is False
    campaign = create_campaign(
        db,
        ctx,
        user,
        CampaignCreate(name="Bygg Göteborg", industry="Bygg", region="Göteborg"),
        request_id="req-campaign",
    )
    prospect = create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(
            campaign_id=campaign["id"],
            company_name="Exempel Bygg AB",
            website_url="https://example.org/",
            industry="Bygg",
            city="Göteborg",
            qualification_score=72,
            estimated_value_sek=48_000,
            contact_name="Anna Andersson",
            contact_role="VD",
            contact_email="anna@example.org",
            contact_verified=True,
            contact_verification_source="operator-confirmed company page",
            legitimate_interest_note="Relevant B2B offer; manual verification before contact.",
        ),
        request_id="req-prospect",
    )
    analysis = run_analysis(
        db,
        ctx,
        user,
        prospect["id"],
        AnalysisRequest(html_snapshot=HTML),
        request_id="req-analysis",
    )
    assert analysis["status"] == "complete"
    assert analysis["snapshot_sha256"]

    proposal = generate_proposal(db, ctx, user, prospect["id"], analysis["id"], request_id="req-proposal")
    assert proposal["status"] == "draft"
    try:
        deliver_proposal(db, ctx, user, proposal["id"], DeliveryRequest(provider="queue"))
    except ProspectingError as exc:
        assert exc.code == "PROPOSAL_NOT_APPROVED"
    else:
        raise AssertionError("Delivery must fail before human approval")

    approved = approve_proposal(
        db,
        ctx,
        user,
        proposal["id"],
        ProposalReview(
            analysis_verified=True,
            contact_verified=True,
            content_approved=True,
            legal_basis_verified=True,
            reviewer_note="Reviewed against evidence packet.",
        ),
        request_id="req-approve",
    )
    assert approved["status"] == "approved"
    assert approved["approved_by_user_id"] == user.id

    share = create_share(db, ctx, user, proposal["id"], 7, request_id="req-share")
    row, prospect_row, analysis_row = public_proposal(db, share["token"])
    rendered = render_proposal_html(row, prospect_row, analysis_row)
    assert "Exempel Bygg AB" in rendered
    assert "noindex" not in rendered  # response headers carry noindex, not customer content

    queued = deliver_proposal(db, ctx, user, proposal["id"], DeliveryRequest(provider="queue", share_token=share["token"]), request_id="req-delivery")
    assert queued["status"] == "queued"
    assert queued["external_sent"] is False

    token = opt_out_token(ctx.tenant_id, prospect["id"], "anna@example.org")
    suppressed = public_opt_out(db, prospect["id"], token)
    assert suppressed["status"] == "suppressed"
    try:
        deliver_proposal(db, ctx, user, proposal["id"], DeliveryRequest(provider="queue"))
    except ProspectingError as exc:
        assert exc.code == "CONTACT_SUPPRESSED"
    else:
        raise AssertionError("Suppressed contacts must never be queued")


def test_duplicate_domain_is_rejected_per_tenant():
    db, ctx, user = _db_and_context()
    payload = ProspectCreate(company_name="First AB", website_url="https://www.example.org/")
    create_prospect(db, ctx, user, payload)
    try:
        create_prospect(db, ctx, user, ProspectCreate(company_name="Duplicate AB", website_url="https://example.org/about"))
    except ProspectingError as exc:
        assert exc.code == "PROSPECT_DOMAIN_DUPLICATE"
    else:
        raise AssertionError("Duplicate domain should be rejected")


def test_pagespeed_enrichment_is_bounded_and_maps_lighthouse(monkeypatch):
    from app.core.config import settings
    import app.prospecting.pagespeed as pagespeed_module

    payload = {
        "lighthouseResult": {
            "fetchTime": "2026-08-15T09:00:00Z",
            "finalUrl": "https://example.se/",
            "categories": {
                "performance": {"score": 0.42},
                "accessibility": {"score": 0.91},
                "seo": {"score": 0.84},
                "best-practices": {"score": 0.76},
            },
            "audits": {
                "largest-contentful-paint": {"displayValue": "3.2 s"},
                "cumulative-layout-shift": {"displayValue": "0.08"},
                "final-screenshot": {"details": {"data": "data:image/jpeg;base64,YWJj"}},
            },
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(settings, "PAGESPEED_API_KEY", "test-key")
    monkeypatch.setattr(pagespeed_module, "urlopen", lambda request, timeout: FakeResponse())
    result = run_pagespeed("https://example.se")
    assert result is not None
    assert result["strategy"] == "mobile"
    assert result["scores"] == {"performance": 42, "accessibility": 91, "seo": 84, "best_practices": 76}
    assert result["web_vitals"]["largest_contentful_paint"] == "3.2 s"
    assert result["final_screenshot"].startswith("data:image/jpeg")

    payload["lighthouseResult"]["audits"]["final-screenshot"]["details"]["data"] = "data:image/png;base64," + ("a" * 750_001)
    assert run_pagespeed("https://example.se")["final_screenshot"] is None


def test_pagespeed_rejects_oversized_provider_response(monkeypatch):
    from app.core.config import settings
    import app.prospecting.pagespeed as pagespeed_module

    class OversizedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return b"x" * 6_000_001

    monkeypatch.setattr(settings, "PAGESPEED_API_KEY", "test-key")
    monkeypatch.setattr(pagespeed_module, "urlopen", lambda request, timeout: OversizedResponse())
    try:
        run_pagespeed("https://example.se")
        assert False, "Expected bounded PageSpeed response rejection"
    except PageSpeedError as exc:
        assert "size limit" in str(exc)


def test_resend_delivery_uses_idempotency_and_one_click_headers(monkeypatch):
    from app.core.config import settings
    import app.prospecting.outbound as outbound_module

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return b'{"id":"email_123"}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(settings, "PROSPECTING_REAL_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_API_KEY", "secret-provider-key")
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_FROM", "SalesOS <sales@example.se>")
    monkeypatch.setattr(outbound_module, "urlopen", fake_urlopen)
    receipt = deliver_email(
        provider="resend",
        recipient="kontakt@example.se",
        subject="Förslag",
        text_body="Personligt förslag",
        html_body="<p>Personligt förslag</p>",
        unsubscribe_url="https://salesos.example.se/api/v1/public/prospecting/opt-out/id/token",
        idempotency_key="prospecting-1-proposal-abc",
    )
    assert receipt.external_sent is True
    request = captured["request"]
    assert request.get_header("Idempotency-key") == "prospecting-1-proposal-abc"
    body = json.loads(request.data)
    assert body["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert body["headers"]["List-Unsubscribe"].startswith("<https://")


def test_public_capability_tokens_are_redacted_from_application_logs():
    token = "secret-share-capability-token"
    assert token not in _safe_log_path(f"/api/v1/public/prospecting/proposals/{token}")
    assert token not in _safe_log_path(f"/api/v1/public/prospecting/opt-out/prospect/{token}")
    assert _safe_log_path("/api/v1/prospecting/summary") == "/api/v1/prospecting/summary"
