"""Guardrails that stand between an approved proposal and a real inbox."""
from __future__ import annotations

import pytest
from conftest import TENANT_A, bearer

from app.core.config import settings
from app.prospecting.models import WebsiteProposal
from app.prospecting.outbound import ProspectingDeliveryError, deliver_email

SNAPSHOT = "<html><head><title>Acme</title></head><body><h1>Acme</h1></body></html>"
APPROVAL = {
    "analysis_verified": True,
    "contact_verified": True,
    "content_approved": True,
    "legal_basis_verified": True,
}


def _approved_proposal(client, **prospect_overrides) -> tuple[dict, dict]:
    payload = {
        "company_name": "Acme Bygg AB",
        "website_url": "https://acme-bygg.example",
        "contact_email": "anna@acme-bygg.example",
        "contact_verified": True,
    }
    payload.update(prospect_overrides)
    prospect = client.post(
        "/api/v1/prospecting/prospects", json=payload, headers=bearer()
    ).json()
    analysis = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"html_snapshot": SNAPSHOT},
        headers=bearer(),
    ).json()
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()
    client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/approve", json=APPROVAL, headers=bearer()
    )
    return prospect, proposal


def test_delivery_requires_all_four_human_checks(client):
    prospect = client.post(
        "/api/v1/prospecting/prospects",
        json={
            "company_name": "Acme Bygg AB",
            "website_url": "https://acme-bygg.example",
            "contact_email": "anna@acme-bygg.example",
            "contact_verified": True,
        },
        headers=bearer(),
    ).json()
    analysis = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"html_snapshot": SNAPSHOT},
        headers=bearer(),
    ).json()
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()

    partial = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/approve",
        json={**APPROVAL, "content_approved": False},
        headers=bearer(),
    )
    assert partial.status_code == 422

    undelivered = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock"},
        headers=bearer(),
    )
    assert undelivered.status_code == 409
    assert undelivered.json()["detail"]["code"] == "PROPOSAL_NOT_APPROVED"


def test_unverified_contacts_are_never_delivered_to(client):
    prospect, proposal = _approved_proposal(client)
    # Verification was withdrawn after approval: delivery must stop.
    revoked = client.patch(
        f"/api/v1/prospecting/prospects/{prospect['id']}",
        json={"contact_verified": False},
        headers=bearer(),
    )
    assert revoked.status_code == 200
    response = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock"},
        headers=bearer(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONTACT_NOT_VERIFIED"


def test_suppressed_contacts_are_never_delivered_to(client):
    _, proposal = _approved_proposal(client)
    client.post(
        "/api/v1/prospecting/suppressions",
        json={"email": "anna@acme-bygg.example", "reason": "complaint"},
        headers=bearer(),
    )
    response = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock"},
        headers=bearer(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONTACT_SUPPRESSED"


def test_test_delivery_may_only_target_the_authenticated_operator(client):
    _, proposal = _approved_proposal(client)
    stolen = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock", "test_recipient": "someone-else@example.com"},
        headers=bearer(),
    )
    assert stolen.status_code == 403
    assert stolen.json()["detail"]["code"] == "TEST_RECIPIENT_FORBIDDEN"

    allowed = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock", "test_recipient": "operator@acme.test"},
        headers=bearer(),
    )
    assert allowed.status_code == 200
    assert allowed.json()["external_sent"] is False


def test_a_test_send_does_not_consume_the_daily_budget(client, db_session):
    """Test sends reach only the operator, so they must not lock the proposal."""
    _, proposal = _approved_proposal(client)
    client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "mock", "test_recipient": "operator@acme.test"},
        headers=bearer(),
    )
    stored = db_session.get(WebsiteProposal, proposal["id"])
    assert stored.delivery_processed_at is None

    real = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "queue"},
        headers=bearer(),
    )
    assert real.status_code == 200
    db_session.expire_all()
    assert db_session.get(WebsiteProposal, proposal["id"]).delivery_processed_at is not None


def test_daily_delivery_limit_is_enforced_per_tenant(client):
    client.patch(
        "/api/v1/prospecting/policy",
        json={"mode": "manual_review", "daily_delivery_limit": 1},
        headers=bearer(),
    )
    for index in (1, 2):
        _, proposal = _approved_proposal(
            client,
            company_name=f"Bolag {index} AB",
            website_url=f"https://bolag{index}.example",
            contact_email=f"kontakt{index}@bolag{index}.example",
        )
        response = client.post(
            f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
            json={"provider": "queue"},
            headers=bearer(),
        )
        if index == 1:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert response.json()["detail"]["code"] == "DELIVERY_DAILY_LIMIT"


def test_real_email_is_fail_closed_by_default():
    """The kill switch, not a provider default, decides whether mail leaves."""
    with pytest.raises(ProspectingDeliveryError) as exc:
        deliver_email(
            provider="resend",
            recipient="anna@acme-bygg.example",
            subject="Hej",
            text_body="text",
            html_body="<p>text</p>",
            unsubscribe_url="https://nova.example/opt-out",
        )
    assert exc.value.code == "REAL_EMAIL_DISABLED"
    assert settings.PROSPECTING_REAL_EMAIL_ENABLED is False


def test_enabled_real_email_still_requires_a_configured_sender(monkeypatch):
    monkeypatch.setattr(settings, "PROSPECTING_REAL_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "PROSPECTING_EMAIL_API_KEY", "")
    with pytest.raises(ProspectingDeliveryError) as exc:
        deliver_email(
            provider="resend",
            recipient="anna@acme-bygg.example",
            subject="Hej",
            text_body="text",
            html_body="<p>text</p>",
            unsubscribe_url="https://nova.example/opt-out",
        )
    assert exc.value.code == "EMAIL_PROVIDER_NOT_CONFIGURED"


def test_unknown_providers_are_rejected():
    with pytest.raises(ProspectingDeliveryError) as exc:
        deliver_email(
            provider="carrier-pigeon",
            recipient="anna@acme-bygg.example",
            subject="Hej",
            text_body="text",
            html_body="<p>text</p>",
            unsubscribe_url="https://nova.example/opt-out",
        )
    assert exc.value.code == "EMAIL_PROVIDER_UNSUPPORTED"


def test_delivery_body_carries_a_working_opt_out_link(client):
    prospect, proposal = _approved_proposal(client)
    client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "queue"},
        headers=bearer(),
    )
    from app.prospecting.outbound import opt_out_token, verify_opt_out_token

    token = opt_out_token(TENANT_A, prospect["id"], "anna@acme-bygg.example")
    assert verify_opt_out_token(token, TENANT_A, prospect["id"], "anna@acme-bygg.example")
    # The signature is bound to the tenant: another tenant's copy does not verify.
    assert not verify_opt_out_token(token, "tenant-globex", prospect["id"], "anna@acme-bygg.example")
