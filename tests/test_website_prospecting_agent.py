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
from app.prospecting.outbound import ProspectingDeliveryError, deliver_email, opt_out_token
from app.prospecting.pagespeed import PageSpeedError, run_pagespeed
from app.prospecting.presentation import build_meeting_story, render_meeting_presentation_html
from app.prospecting.schemas import (
    AnalysisRequest,
    CampaignCreate,
    DeliveryRequest,
    ProspectBulkCsvRequest,
    ProspectCreate,
    ProspectPromoteRequest,
    ProspectingPolicyUpdate,
    ProposalReview,
)
from app.prospecting.service import (
    ProspectingError,
    approve_proposal,
    bulk_create_prospects_from_csv,
    create_campaign,
    create_prospect,
    create_share,
    deliver_proposal,
    generate_proposal,
    get_policy,
    list_prospects,
    promote_prospect_to_crm,
    public_opt_out,
    public_proposal,
    render_proposal_html,
    run_analysis,
    update_policy,
)
from app.models.sales_desk import SalesDeskCase, SalesDeskCustomer, SalesDeskLead
from app.prospecting.models import WebsiteProspect
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
        "/api/v1/prospecting/prospects/{prospect_id}/promote",
        "/api/v1/prospecting/prospects/bulk-csv",
        "/api/v1/prospecting/proposals/{proposal_id}/approve",
        "/api/v1/prospecting/proposals/{proposal_id}/deliver",
        "/api/v1/prospecting/proposals/{proposal_id}/presentation",
        "/api/v1/public/prospecting/proposals/{token}",
        "/api/v1/public/prospecting/presentations/{token}",
        "/api/v1/public/prospecting/opt-out/{prospect_id}/{token}",
    }
    assert required <= set(paths)
    assert "security" in paths["/api/v1/prospecting/summary"]["get"]
    assert "security" in paths["/api/v1/prospecting/proposals/{proposal_id}/presentation"]["get"]
    assert "security" not in paths["/api/v1/public/prospecting/proposals/{token}"]["get"]
    assert "security" not in paths["/api/v1/public/prospecting/presentations/{token}"]["get"]


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
    story = build_meeting_story(row, prospect_row, analysis_row)
    assert story["company"] == "Exempel Bygg AB"
    assert len(story["scenes"]) == 9
    assert story["duration_seconds"] >= 120
    assert next(scene for scene in story["scenes"] if scene["id"] == "structure")["visual"] == "comparison"
    roadmap = next(scene for scene in story["scenes"] if scene["id"] == "roadmap")
    assert any(card["label"] == "Investering" for card in roadmap["cards"])
    assert all(card["label"] != "Break-even" for card in roadmap["cards"])
    meeting_film = render_meeting_presentation_html(row, prospect_row, analysis_row)
    assert "Nova · kundmöte" in meeting_film
    assert "Starta i helskärm" in meeting_film
    assert "Målbild · koncept" in meeting_film
    assert "täckningsbidrag" not in meeting_film.lower()
    assert "break-even" not in meeting_film.lower()
    assert "calculateBreakEven" not in meeting_film
    assert "speechSynthesis" in meeting_film

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


def test_list_prospects_includes_latest_analysis_and_proposal():
    db, ctx, user = _db_and_context()
    prospect = create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(company_name="Exempel Bygg AB", website_url="https://example.org/"),
        request_id="req-list-prospect",
    )
    analysis = run_analysis(
        db,
        ctx,
        user,
        prospect["id"],
        AnalysisRequest(html_snapshot=HTML),
        request_id="req-list-analysis",
    )
    proposal = generate_proposal(db, ctx, user, prospect["id"], analysis["id"], request_id="req-list-proposal")
    listed = list_prospects(db, ctx)
    assert len(listed) == 1
    assert listed[0]["id"] == prospect["id"]
    assert listed[0]["latest_analysis"] is not None
    assert listed[0]["latest_analysis"]["id"] == analysis["id"]
    assert listed[0]["latest_analysis"]["status"] == "complete"
    assert listed[0]["latest_proposal"] is not None
    assert listed[0]["latest_proposal"]["id"] == proposal["id"]


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


def test_smtp_generic_is_rejected_when_kill_switch_is_off(monkeypatch):
    from app.core.config import settings
    import app.prospecting.outbound as outbound_module

    monkeypatch.setattr(settings, "PROSPECTING_REAL_EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_PROVIDER", "smtp_generic")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "operator@example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_PASSWORD", "not-a-real-password")

    def fail_smtp(*_args, **_kwargs):
        raise AssertionError("SMTP must not open a socket when the kill switch is off")

    monkeypatch.setattr(outbound_module.smtplib, "SMTP", fail_smtp)
    try:
        deliver_email(
            provider="smtp_generic",
            recipient="kontakt@example.se",
            subject="Förslag",
            text_body="Personligt förslag",
            html_body="<p>Personligt förslag</p>",
            unsubscribe_url="https://salesos.example.se/api/v1/public/prospecting/opt-out/id/token",
            from_address="operator@example.test",
        )
        assert False, "Expected kill-switch rejection"
    except ProspectingDeliveryError as exc:
        assert exc.code == "REAL_EMAIL_DISABLED"


def test_smtp_generic_uses_allowlisted_mailbox_without_network(monkeypatch):
    from app.core.config import settings
    import app.prospecting.outbound as outbound_module

    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captured["host"] = host
            captured["port"] = port
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def starttls(self):
            captured["starttls"] = True

        def login(self, user, password):
            captured["user"] = user
            captured["password"] = password

        def send_message(self, message):
            captured["from"] = message["From"]
            captured["to"] = message["To"]
            captured["unsubscribe"] = message["List-Unsubscribe"]

    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "PROSPECTING_REAL_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_PROVIDER", "smtp_generic")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_PORT", 587)
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_STARTTLS", True)
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "operator@example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(outbound_module.smtplib, "SMTP", FakeSMTP)
    receipt = deliver_email(
        provider="smtp_generic",
        recipient="kontakt@example.se",
        subject="Förslag",
        text_body="Personligt förslag",
        html_body="<p>Personligt förslag</p>",
        unsubscribe_url="https://salesos.example.se/api/v1/public/prospecting/opt-out/id/token",
        from_address="operator@example.test",
    )
    assert receipt.external_sent is True
    assert receipt.provider == "smtp_generic"
    assert captured["host"] == "mail.example.test"
    assert captured["user"] == "operator@example.test"
    assert captured["from"] == "operator@example.test"
    assert captured["unsubscribe"].startswith("<https://")


def test_smtp_generic_production_env_uses_allowlisted_mailbox_without_network(monkeypatch):
    from app.core.config import settings
    import app.prospecting.outbound as outbound_module

    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captured["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def starttls(self):
            captured["starttls"] = True

        def login(self, user, password):
            captured["user"] = user

        def send_message(self, message):
            captured["from"] = message["From"]

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "PROSPECTING_REAL_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_PROVIDER", "smtp_generic")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_PORT", 587)
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_STARTTLS", True)
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "operator@example.test")
    monkeypatch.setattr(settings, "PROSPECTING_SMTP_MAILBOX_1_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(outbound_module.smtplib, "SMTP", FakeSMTP)
    receipt = deliver_email(
        provider="smtp_generic",
        recipient="kontakt@example.se",
        subject="Förslag",
        text_body="Personligt förslag",
        html_body="<p>Personligt förslag</p>",
        unsubscribe_url="https://salesos.se/api/v1/public/prospecting/opt-out/id/token",
        from_address="operator@example.test",
    )
    assert receipt.external_sent is True
    assert receipt.provider == "smtp_generic"
    assert captured["user"] == "operator@example.test"
    assert captured["from"] == "operator@example.test"


def test_public_capability_tokens_are_redacted_from_application_logs():
    token = "secret-share-capability-token"
    assert token not in _safe_log_path(f"/api/v1/public/prospecting/proposals/{token}")
    assert token not in _safe_log_path(f"/api/v1/public/prospecting/opt-out/prospect/{token}")
    assert _safe_log_path("/api/v1/prospecting/summary") == "/api/v1/prospecting/summary"


def test_promote_prospect_creates_crm_customer_lead_and_case():
    db, ctx, user = _db_and_context()
    prospect = create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(
            company_name="Promote Test AB",
            website_url="https://promote-test.example.invalid/",
            contact_email="secret@example.invalid",
            contact_verified=False,
        ),
        request_id="promote-1",
    )
    result = promote_prospect_to_crm(
        db,
        ctx,
        user,
        prospect["id"],
        ProspectPromoteRequest(vertical_id="kitchen", brand_id="formkok"),
        request_id="promote-1",
    )
    assert result["already_promoted"] is False
    assert result["prospect_id"] == prospect["id"]
    customer = db.query(SalesDeskCustomer).filter(SalesDeskCustomer.id == result["customer_id"]).one()
    lead = db.query(SalesDeskLead).filter(SalesDeskLead.id == result["lead_id"]).one()
    case = db.query(SalesDeskCase).filter(SalesDeskCase.id == result["case_id"]).one()
    assert customer.tenant_id == ctx.tenant_id
    assert customer.name == "Promote Test AB"
    assert customer.email is None  # contact email not copied unless verified+requested
    assert lead.source == f"prospecting:{prospect['id']}"
    assert case.lead_id == lead.id
    assert case.title.startswith("Nova —")
    assert db.query(WebsiteProspect).filter(WebsiteProspect.id == prospect["id"]).one().status == "contacted"

    again = promote_prospect_to_crm(
        db,
        ctx,
        user,
        prospect["id"],
        ProspectPromoteRequest(vertical_id="kitchen", brand_id="formkok"),
        request_id="promote-2",
    )
    assert again["already_promoted"] is True
    assert again["lead_id"] == result["lead_id"]
    assert again["case_id"] == result["case_id"]
    assert db.query(SalesDeskLead).count() == 1


def test_promote_respects_do_not_contact_and_optional_verified_email():
    db, ctx, user = _db_and_context()
    blocked = create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(company_name="Blocked AB", website_url="https://blocked.example.invalid/"),
        request_id="promote-dnc",
    )
    row = db.query(WebsiteProspect).filter(WebsiteProspect.id == blocked["id"]).one()
    row.do_not_contact = True
    db.commit()
    try:
        promote_prospect_to_crm(
            db,
            ctx,
            user,
            blocked["id"],
            ProspectPromoteRequest(vertical_id="kitchen", brand_id="formkok"),
        )
        assert False, "expected ProspectingError"
    except ProspectingError as exc:
        assert exc.code == "PROSPECT_DO_NOT_CONTACT"

    ok = create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(
            company_name="Verified Contact AB",
            website_url="https://verified.example.invalid/",
            contact_email="owner@verified.example.invalid",
            contact_verified=True,
        ),
        request_id="promote-email",
    )
    result = promote_prospect_to_crm(
        db,
        ctx,
        user,
        ok["id"],
        ProspectPromoteRequest(vertical_id="kitchen", brand_id="formkok", include_contact_email=True),
        request_id="promote-email",
    )
    customer = db.query(SalesDeskCustomer).filter(SalesDeskCustomer.id == result["customer_id"]).one()
    assert customer.email == "owner@verified.example.invalid"


def test_bulk_csv_intake_creates_skips_duplicate_ignores_email():
    db, ctx, user = _db_and_context()
    create_prospect(
        db,
        ctx,
        user,
        ProspectCreate(company_name="Existing AB", website_url="https://existing.example.invalid/"),
        request_id="csv-seed",
    )
    csv_text = (
        "company_name,website_url,city,contact_email\n"
        "Alpha AB,https://alpha.example.invalid/,Göteborg,secret@alpha.example.invalid\n"
        "Beta AB,https://beta.example.invalid/,Malmö,\n"
        "Dup Existing,https://existing.example.invalid/,Stockholm,\n"
        "Bad Row,not-a-url,,\n"
        "Alpha Again,https://alpha.example.invalid/about,,\n"
    )
    result = bulk_create_prospects_from_csv(
        db,
        ctx,
        user,
        ProspectBulkCsvRequest(csv_text=csv_text),
        request_id="csv-bulk",
    )
    assert result["row_count"] == 5
    assert len(result["created"]) == 2
    assert {item["normalized_domain"] for item in result["created"]} == {
        "alpha.example.invalid",
        "beta.example.invalid",
    }
    assert all(item["source_provider"] == "csv_manual" for item in result["created"])
    assert all(item["contact_email"] is None for item in result["created"])
    reasons = {item["reason"] for item in result["skipped"]}
    assert "duplicate_domain" in reasons
    assert "website_invalid" in reasons
    assert "duplicate_in_batch" in reasons

    try:
        bulk_create_prospects_from_csv(
            db,
            ctx,
            user,
            ProspectBulkCsvRequest(csv_text="website_url\nhttps://only.example.invalid/\n"),
            request_id="csv-bad-header",
        )
        assert False, "expected ProspectingError"
    except ProspectingError as exc:
        assert exc.code == "CSV_COLUMNS_REQUIRED"

    too_many = "company_name,website_url\n" + "".join(
        f"Co {i},https://co{i}.example.invalid/\n" for i in range(51)
    )
    try:
        bulk_create_prospects_from_csv(
            db,
            ctx,
            user,
            ProspectBulkCsvRequest(csv_text=too_many),
            request_id="csv-too-many",
        )
        assert False, "expected ProspectingError"
    except ProspectingError as exc:
        assert exc.code == "CSV_TOO_MANY_ROWS"
