"""Tenant isolation: identifiers from another tenant must be unreachable.

Nova derives the tenant from the signed token only. These tests take real ids
created by tenant A and replay them with tenant B's token through every route
that accepts an id, which is exactly the shape of a cross-tenant IDOR attempt.
"""
from __future__ import annotations

import pytest
from conftest import TENANT_A, TENANT_B, bearer

SNAPSHOT = "<html><head><title>Acme</title></head><body><h1>Acme</h1></body></html>"


@pytest.fixture()
def tenant_a_records(client) -> dict:
    prospect = client.post(
        "/api/v1/prospecting/prospects",
        json={
            "company_name": "Acme Bygg AB",
            "website_url": "https://acme-bygg.example",
            "contact_email": "anna@acme-bygg.example",
            "contact_verified": True,
        },
        headers=bearer(TENANT_A),
    ).json()
    campaign = client.post(
        "/api/v1/prospecting/campaigns", json={"name": "A-kampanj"}, headers=bearer(TENANT_A)
    ).json()
    analysis = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"html_snapshot": SNAPSHOT},
        headers=bearer(TENANT_A),
    ).json()
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(TENANT_A),
    ).json()
    return {
        "prospect": prospect,
        "campaign": campaign,
        "analysis": analysis,
        "proposal": proposal,
    }


def test_foreign_ids_are_not_readable(client, tenant_a_records):
    prospect_id = tenant_a_records["prospect"]["id"]
    proposal_id = tenant_a_records["proposal"]["id"]
    other = bearer(TENANT_B, subject="operator@globex.test")

    assert client.get(f"/api/v1/prospecting/prospects/{prospect_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/prospecting/proposals/{proposal_id}", headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/prospecting/prospects/{prospect_id}/analyses", headers=other).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/prospecting/prospects/{prospect_id}/proposals", headers=other).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/prospecting/proposals/{proposal_id}/presentation", headers=other
        ).status_code
        == 404
    )


def test_foreign_ids_are_not_writable(client, tenant_a_records):
    prospect_id = tenant_a_records["prospect"]["id"]
    proposal_id = tenant_a_records["proposal"]["id"]
    campaign_id = tenant_a_records["campaign"]["id"]
    other = bearer(TENANT_B, subject="operator@globex.test")

    assert (
        client.patch(
            f"/api/v1/prospecting/prospects/{prospect_id}",
            json={"status": "won"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/prospecting/proposals/{proposal_id}",
            json={"headline": "Overtaget forslag"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/prospecting/prospects/{prospect_id}/analyses",
            json={"html_snapshot": SNAPSHOT},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/prospecting/prospects/{prospect_id}/proposals",
            json={},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/prospecting/proposals/{proposal_id}/approve",
            json={
                "analysis_verified": True,
                "contact_verified": True,
                "content_approved": True,
                "legal_basis_verified": True,
            },
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/prospecting/proposals/{proposal_id}/share",
            json={"expires_in_days": 5},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/prospecting/proposals/{proposal_id}/deliver",
            json={"provider": "mock"},
            headers=other,
        ).status_code
        == 404
    )
    # A campaign reference is validated against the caller's tenant too.
    assert (
        client.post(
            "/api/v1/prospecting/prospects",
            json={
                "company_name": "Globex AB",
                "website_url": "https://globex.example",
                "campaign_id": campaign_id,
            },
            headers=other,
        ).status_code
        == 404
    )


def test_listings_and_counters_never_cross_tenants(client, tenant_a_records):
    other = bearer(TENANT_B, subject="operator@globex.test")
    assert client.get("/api/v1/prospecting/prospects", headers=other).json() == []
    assert client.get("/api/v1/prospecting/campaigns", headers=other).json() == []
    summary = client.get("/api/v1/prospecting/summary", headers=other).json()
    assert summary["analyzed_sites"] == 0
    assert summary["qualified_opportunities"] == 0
    assert summary["potential_value_sek"] == 0
    assert summary["awaiting_review"] == 0


def test_query_parameter_cannot_redirect_the_tenant(client, tenant_a_records):
    """?tenant_id may only restate the token's tenant, never replace it."""
    forged = client.get(
        f"/api/v1/prospecting/prospects?tenant_id={TENANT_A}",
        headers=bearer(TENANT_B, subject="operator@globex.test"),
    )
    assert forged.status_code == 403
    assert forged.json()["detail"] == "Tenant access denied"

    agreeing = client.get(
        f"/api/v1/prospecting/prospects?tenant_id={TENANT_A}", headers=bearer(TENANT_A)
    )
    assert agreeing.status_code == 200
    assert len(agreeing.json()) == 1


def test_suppression_lists_are_tenant_scoped(client):
    email = "kontakt@delad.example"
    assert (
        client.post(
            "/api/v1/prospecting/suppressions", json={"email": email}, headers=bearer(TENANT_A)
        ).status_code
        == 201
    )
    a_summary = client.get("/api/v1/prospecting/summary", headers=bearer(TENANT_A)).json()
    b_summary = client.get(
        "/api/v1/prospecting/summary", headers=bearer(TENANT_B, subject="operator@globex.test")
    ).json()
    assert a_summary["suppressed_contacts"] == 1
    assert b_summary["suppressed_contacts"] == 0


def test_policy_is_per_tenant(client):
    updated = client.patch(
        "/api/v1/prospecting/policy",
        json={"mode": "rules_assisted", "daily_delivery_limit": 3},
        headers=bearer(TENANT_A),
    )
    assert updated.status_code == 200
    assert updated.json()["daily_delivery_limit"] == 3
    other = client.get(
        "/api/v1/prospecting/policy", headers=bearer(TENANT_B, subject="operator@globex.test")
    ).json()
    assert other["daily_delivery_limit"] == 20
    assert other["mode"] == "manual_review"


def test_share_tokens_do_not_expose_another_tenants_proposal(client, tenant_a_records):
    """A public share is bound to its own proposal, not to a guessable id."""
    proposal_id = tenant_a_records["proposal"]["id"]
    client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/approve",
        json={
            "analysis_verified": True,
            "contact_verified": True,
            "content_approved": True,
            "legal_basis_verified": True,
        },
        headers=bearer(TENANT_A),
    )
    token = client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/share",
        json={"expires_in_days": 2},
        headers=bearer(TENANT_A),
    ).json()["token"]
    # The token works publicly, but tenant B still cannot reach the record.
    assert client.get(f"/api/v1/public/prospecting/proposals/{token}").status_code == 200
    assert (
        client.get(
            f"/api/v1/prospecting/proposals/{proposal_id}",
            headers=bearer(TENANT_B, subject="operator@globex.test"),
        ).status_code
        == 404
    )
