"""Route-level security and workflow tests for website prospecting."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

from starlette.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import auth
from app.db.session import Base, get_db
from app.main import app
from app.models.tenancy import TenantMembership
from app.models.user import User
from app.prospecting.models import WebsiteProposal
from helpers.quote_tenant import seed_tenant_member


BASE = "/api/v1/prospecting"


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


@contextmanager
def _workspace():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    admin_a = User(email="prospecting-a@example.se", password_hash="x", role="user")
    admin_b = User(email="prospecting-b@example.se", password_hash="x", role="user")
    viewer_a = User(email="prospecting-viewer@example.se", password_hash="x", role="user")
    db.add_all([admin_a, admin_b, viewer_a])
    db.flush()
    tenant_a = seed_tenant_member(db, admin_a, slug="prospecting-http-a")
    tenant_b = seed_tenant_member(db, admin_b, slug="prospecting-http-b")
    seed_tenant_member(db, viewer_a, slug="unused", tenant=tenant_a)
    viewer_membership = db.query(TenantMembership).filter_by(tenant_id=tenant_a.id, user_id=viewer_a.id).one()
    viewer_membership.role = "tenant_viewer"
    viewer_membership.access_scope = "crm_read_only"
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, db, admin_a, admin_b, viewer_a, tenant_a, tenant_b
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def _prospect_payload(name: str, domain: str, email: str) -> dict:
    return {
        "company_name": name,
        "website_url": f"https://{domain}",
        "contact_name": "Verifierad Kontakt",
        "contact_role": "VD",
        "contact_email": email,
        "contact_verified": True,
        "contact_verification_source": f"https://{domain}/kontakt",
        "legal_basis": "legitimate_interest_b2b",
        "legitimate_interest_note": "Relevant B2B-webbtjänst efter individuell kontroll av företagets publika webbplats.",
        "source_provider": "manual",
        "source_url": f"https://{domain}",
    }


def _approved_proposal(client: TestClient, headers: dict[str, str], *, name: str, domain: str, email: str) -> tuple[str, str]:
    prospect = client.post(f"{BASE}/prospects", headers=headers, json=_prospect_payload(name, domain, email))
    assert prospect.status_code == 201, prospect.text
    prospect_id = prospect.json()["id"]
    analysis = client.post(
        f"{BASE}/prospects/{prospect_id}/analyses",
        headers=headers,
        json={
            "allow_network_fetch": False,
            "html_snapshot": (
                '<!doctype html><html lang="sv"><head><title>Företag</title>'
                '<meta name="description" content="Lokalt tjänsteföretag">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '</head><body><h1>Trygg lokal hjälp</h1><p>Kontakta oss för offert.</p>'
                '<a href="/kontakt">Kontakta oss</a></body></html>'
            ),
        },
    )
    assert analysis.status_code == 201, analysis.text
    proposal = client.post(
        f"{BASE}/prospects/{prospect_id}/proposals",
        headers=headers,
        json={"analysis_id": analysis.json()["id"]},
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["id"]
    approval = client.post(
        f"{BASE}/proposals/{proposal_id}/approve",
        headers=headers,
        json={
            "analysis_verified": True,
            "contact_verified": True,
            "content_approved": True,
            "legal_basis_verified": True,
            "reviewer_note": "Route-level test: samtliga underlag manuellt verifierade.",
        },
    )
    assert approval.status_code == 200, approval.text
    return prospect_id, proposal_id


def test_routes_require_auth_enforce_rbac_and_isolate_tenants():
    with _workspace() as (client, _, admin_a, admin_b, viewer_a, tenant_a, tenant_b):
        assert client.get(f"{BASE}/summary").status_code == 401
        headers_a = _headers(admin_a)
        headers_b = _headers(admin_b)
        headers_viewer = _headers(viewer_a)

        created_a = client.post(
            f"{BASE}/prospects",
            headers=headers_a,
            json=_prospect_payload("Tenant A AB", "tenant-a.example.se", "kontakt@tenant-a.example.se"),
        )
        created_b = client.post(
            f"{BASE}/prospects",
            headers=headers_b,
            json=_prospect_payload("Tenant B AB", "tenant-b.example.se", "kontakt@tenant-b.example.se"),
        )
        assert created_a.status_code == created_b.status_code == 201
        assert [item["company_name"] for item in client.get(f"{BASE}/prospects", headers=headers_a).json()] == ["Tenant A AB"]
        assert [item["company_name"] for item in client.get(f"{BASE}/prospects", headers=headers_b).json()] == ["Tenant B AB"]
        assert client.get(f"{BASE}/prospects?tenant_id={tenant_b.id}", headers=headers_a).status_code == 403

        viewer_list = client.get(f"{BASE}/prospects?tenant_id={tenant_a.id}", headers=headers_viewer)
        assert viewer_list.status_code == 200
        denied = client.patch(
            f"{BASE}/policy?tenant_id={tenant_a.id}",
            headers=headers_viewer,
            json={"mode": "rules_assisted", "daily_delivery_limit": 5},
        )
        assert denied.status_code == 403
        assert "PROSPECTING_WRITE_FORBIDDEN" in denied.text


def test_contact_verification_and_operator_suppression_routes():
    with _workspace() as (client, _, admin_a, *_):
        headers = _headers(admin_a)
        payload = _prospect_payload("Kontaktflöde AB", "kontaktflode.example.se", "person@kontaktflode.example.se")
        payload.update({"contact_verified": False, "contact_verification_source": None})
        created = client.post(f"{BASE}/prospects", headers=headers, json=payload)
        assert created.status_code == 201
        prospect_id = created.json()["id"]

        verified = client.patch(
            f"{BASE}/prospects/{prospect_id}",
            headers={**headers, "X-Request-ID": "verify-contact-http"},
            json={"contact_verified": True, "contact_verification_source": "Företagets kontaktsida kontrollerad 2026-08-15"},
        )
        assert verified.status_code == 200
        assert verified.json()["contact_verified"] is True

        suppressed = client.post(
            f"{BASE}/suppressions",
            headers=headers,
            json={"prospect_id": prospect_id, "email": payload["contact_email"], "reason": "operator"},
        )
        assert suppressed.status_code == 201
        stored = client.get(f"{BASE}/prospects/{prospect_id}", headers=headers)
        assert stored.status_code == 200
        assert stored.json()["do_not_contact"] is True


def test_share_security_duplicate_delivery_and_daily_limit(monkeypatch):
    # Policy JSON mirrors process settings; isolate from developer .env real-email flags.
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "PROSPECTING_REAL_EMAIL_ENABLED", False)
    with _workspace() as (client, db, admin_a, *_):
        headers = _headers(admin_a)
        policy = client.patch(
            f"{BASE}/policy",
            headers=headers,
            json={
                "mode": "rules_assisted",
                "auto_analyze": True,
                "auto_generate_proposal": True,
                "auto_queue_after_approval": True,
                "minimum_score": 80,
                "daily_delivery_limit": 1,
            },
        )
        assert policy.status_code == 200
        assert policy.json()["scheduler_enabled"] is False
        assert policy.json()["real_email_enabled"] is False

        _, proposal_one = _approved_proposal(
            client,
            headers,
            name="Leverans Ett AB",
            domain="leverans-ett.example.se",
            email="ett@leverans-ett.example.se",
        )
        operator_preview = client.get(f"{BASE}/proposals/{proposal_one}/presentation", headers=headers)
        assert operator_preview.status_code == 200
        assert operator_preview.headers["cache-control"] == "private, no-store, max-age=0"
        assert "Starta i helskärm" in operator_preview.text
        assert client.get(f"{BASE}/proposals/{proposal_one}/presentation").status_code == 401

        share = client.post(f"{BASE}/proposals/{proposal_one}/share", headers=headers, json={"expires_in_days": 14})
        assert share.status_code == 200
        token = share.json()["token"]
        assert share.json()["presentation_path"] == f"/api/v1/public/prospecting/presentations/{token}"
        public = client.get(f"/api/v1/public/prospecting/proposals/{token}")
        assert public.status_code == 200
        assert public.headers["cache-control"] == "private, no-store, max-age=0"
        assert public.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
        assert "frame-ancestors 'none'" in public.headers["content-security-policy"]
        assert "Spara som PDF" in public.text
        assert "Starta den kundanpassade mötesfilmen" in public.text
        assert client.get("/api/v1/public/prospecting/proposals/not-a-token").status_code == 404

        meeting_film = client.get(f"/api/v1/public/prospecting/presentations/{token}")
        assert meeting_film.status_code == 200
        assert meeting_film.headers["cache-control"] == "private, no-store, max-age=0"
        assert meeting_film.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
        assert "script-src 'unsafe-inline'" in meeting_film.headers["content-security-policy"]
        assert "connect-src 'none'" in meeting_film.headers["content-security-policy"]
        assert "Leverans Ett AB" in meeting_film.text
        assert "Starta i helskärm" in meeting_film.text
        assert "täckningsbidrag" not in meeting_film.text.lower()
        assert "break-even" not in meeting_film.text.lower()
        assert client.get("/api/v1/public/prospecting/presentations/not-a-token").status_code == 404

        first_delivery = client.post(
            f"{BASE}/proposals/{proposal_one}/deliver",
            headers=headers,
            json={"provider": "queue", "share_token": token},
        )
        assert first_delivery.status_code == 200
        assert first_delivery.json()["external_sent"] is False
        duplicate = client.post(
            f"{BASE}/proposals/{proposal_one}/deliver",
            headers=headers,
            json={"provider": "queue", "share_token": token},
        )
        assert duplicate.status_code == 409
        assert "DELIVERY_ALREADY_PROCESSED" in duplicate.text

        _, proposal_two = _approved_proposal(
            client,
            headers,
            name="Leverans Två AB",
            domain="leverans-tva.example.se",
            email="tva@leverans-tva.example.se",
        )
        limited = client.post(f"{BASE}/proposals/{proposal_two}/deliver", headers=headers, json={"provider": "queue"})
        assert limited.status_code == 429
        assert "DELIVERY_DAILY_LIMIT" in limited.text

        row = db.query(WebsiteProposal).filter_by(id=proposal_one).one()
        row.share_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        expired = client.get(f"/api/v1/public/prospecting/proposals/{token}")
        expired_film = client.get(f"/api/v1/public/prospecting/presentations/{token}")
        # Expired and unknown links are deliberately indistinguishable to public callers.
        assert expired.status_code == expired_film.status_code == 404
        assert "SHARE_NOT_FOUND" in expired.text
        assert "SHARE_NOT_FOUND" in expired_film.text


def test_test_recipient_delivery_bypasses_duplicate_and_daily_limit():
    with _workspace() as (client, _, admin_a, *_):
        headers = _headers(admin_a)
        _, proposal_id = _approved_proposal(
            client,
            headers,
            name="Testleverans AB",
            domain="testleverans.example.se",
            email="kontakt@testleverans.example.se",
        )
        first = client.post(
            f"{BASE}/proposals/{proposal_id}/deliver",
            headers=headers,
            json={"provider": "queue", "test_recipient": admin_a.email},
        )
        assert first.status_code == 200
        assert first.json()["recipient"] == admin_a.email
        assert first.json()["external_sent"] is False
        second = client.post(
            f"{BASE}/proposals/{proposal_id}/deliver",
            headers=headers,
            json={"provider": "queue", "test_recipient": admin_a.email},
        )
        assert second.status_code == 200
        wrong_recipient = client.post(
            f"{BASE}/proposals/{proposal_id}/deliver",
            headers=headers,
            json={"provider": "queue", "test_recipient": "other@example.invalid"},
        )
        assert wrong_recipient.status_code == 403
        assert "TEST_RECIPIENT_FORBIDDEN" in wrong_recipient.text
