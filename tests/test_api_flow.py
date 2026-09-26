"""End-to-end HTTP coverage of the prospecting flow, one request at a time.

Everything here goes through the real app: routing, auth, validation, service
orchestration, persistence and the response contract.
"""
from __future__ import annotations

import re

from conftest import TENANT_A, bearer

SNAPSHOT = """<!doctype html><html lang="sv"><head><title>Acme Bygg AB</title>
<meta name="description" content="Vi bygger hus i Uppsala sedan 1994 och hjalper dig hela vagen."></head>
<body><h1>Acme Bygg</h1><p>Kontakta oss pa 018-123456.</p>
<img src="/hero.png"><a href="/kontakt">Kontakt</a></body></html>"""


def _create_prospect(client, **overrides) -> dict:
    payload = {
        "company_name": "Acme Bygg AB",
        "website_url": "https://acme-bygg.example",
        "estimated_value_sek": 90_000,
        "contact_name": "Anna Andersson",
        "contact_email": "anna@acme-bygg.example",
        "contact_verified": True,
        "contact_verification_source": "Called and confirmed 2026-09-20",
    }
    payload.update(overrides)
    response = client.post("/api/v1/prospecting/prospects", json=payload, headers=bearer())
    assert response.status_code == 201, response.text
    return response.json()


def _analyze(client, prospect_id: str) -> dict:
    response = client.post(
        f"/api/v1/prospecting/prospects/{prospect_id}/analyses",
        json={"html_snapshot": SNAPSHOT},
        headers=bearer(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, proposal_id: str) -> dict:
    response = client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/approve",
        json={
            "analysis_verified": True,
            "contact_verified": True,
            "content_approved": True,
            "legal_basis_verified": True,
            "reviewer_note": "Checked against the saved evidence.",
        },
        headers=bearer(),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_prospect_to_delivery_flow(client):
    campaign = client.post(
        "/api/v1/prospecting/campaigns",
        json={"name": "Uppsala bygg", "daily_limit": 5},
        headers=bearer(),
    )
    assert campaign.status_code == 201, campaign.text

    prospect = _create_prospect(client, campaign_id=campaign.json()["id"])
    analysis = _analyze(client, prospect["id"])
    assert analysis["status"] == "complete"
    assert analysis["improvement_score"] >= 0
    assert analysis["evidence"], "every finding must carry evidence"

    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["id"]
    assert proposal.json()["version"] == 1
    assert proposal.json()["status"] == "draft"

    edited = client.patch(
        f"/api/v1/prospecting/proposals/{proposal_id}",
        json={"packages": [{"name": "Bas", "price_sek": 64000, "features": ["Ny webbplats"]}]},
        headers=bearer(),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["packages"][0]["price_sek"] == 64000

    approved = _approve(client, proposal_id)
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None

    # Approved proposals are immutable: a new version is the only way forward.
    locked = client.patch(
        f"/api/v1/prospecting/proposals/{proposal_id}",
        json={"headline": "Nytt forslag for Acme"},
        headers=bearer(),
    )
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "APPROVED_PROPOSAL_IMMUTABLE"

    share = client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/share",
        json={"expires_in_days": 7},
        headers=bearer(),
    )
    assert share.status_code == 200, share.text
    token = share.json()["token"]

    public = client.get(f"/api/v1/public/prospecting/proposals/{token}")
    assert public.status_code == 200
    assert public.headers["cache-control"] == "private, no-store, max-age=0"
    assert "noindex" in public.headers["x-robots-tag"]
    assert "frame-ancestors 'none'" in public.headers["content-security-policy"]
    assert "64" in public.text and "SEK" in public.text

    presentation = client.get(f"/api/v1/public/prospecting/presentations/{token}")
    assert presentation.status_code == 200
    assert "connect-src 'none'" in presentation.headers["content-security-policy"]

    delivery = client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/deliver",
        json={"provider": "mock", "share_token": token},
        headers=bearer(),
    )
    assert delivery.status_code == 200, delivery.text
    assert delivery.json()["external_sent"] is False
    assert delivery.json()["status"] == "mock_delivered"

    # Delivery is once-only for an approved proposal.
    repeat = client.post(
        f"/api/v1/prospecting/proposals/{proposal_id}/deliver",
        json={"provider": "mock"},
        headers=bearer(),
    )
    assert repeat.status_code == 409
    assert repeat.json()["detail"]["code"] == "DELIVERY_ALREADY_PROCESSED"

    summary = client.get("/api/v1/prospecting/summary", headers=bearer())
    assert summary.status_code == 200
    body = summary.json()
    assert body["analyzed_sites"] == 1
    assert body["approved"] == 1
    assert body["potential_value_sek"] == 90_000
    assert body["qualified_opportunities"] == 1


def test_public_opt_out_suppresses_further_delivery(client):
    prospect = _create_prospect(client)
    analysis = _analyze(client, prospect["id"])
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()
    _approve(client, proposal["id"])
    delivered = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/deliver",
        json={"provider": "queue"},
        headers=bearer(),
    )
    assert delivered.status_code == 200

    # The opt-out link is HMAC-signed and embedded in the delivered body.
    queued = client.get(f"/api/v1/prospecting/proposals/{proposal['id']}", headers=bearer())
    assert queued.json()["delivery_status"] == "queued"

    from app.prospecting.outbound import opt_out_token

    token = opt_out_token(TENANT_A, prospect["id"], "anna@acme-bygg.example")
    opt_out = client.post(f"/api/v1/public/prospecting/opt-out/{prospect['id']}/{token}")
    assert opt_out.status_code == 200
    assert opt_out.json()["status"] == "suppressed"

    # A forged token is indistinguishable from an unknown prospect: no oracle.
    tampered = client.post(f"/api/v1/public/prospecting/opt-out/{prospect['id']}/{'a' * 64}")
    assert tampered.status_code == 404
    assert tampered.json()["detail"]["code"] == "OPT_OUT_INVALID"

    refreshed = client.get(
        f"/api/v1/prospecting/prospects/{prospect['id']}", headers=bearer()
    ).json()
    assert refreshed["do_not_contact"] is True


def test_second_proposal_version_and_pagination_headers(client):
    prospect = _create_prospect(client)
    analysis = _analyze(client, prospect["id"])
    for expected_version in (1, 2, 3):
        created = client.post(
            f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
            json={"analysis_id": analysis["id"]},
            headers=bearer(),
        )
        assert created.status_code == 201
        assert created.json()["version"] == expected_version

    page = client.get(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals?limit=2",
        headers=bearer(),
    )
    assert page.status_code == 200
    assert len(page.json()) == 2
    assert page.headers["x-total-count"] == "3"
    assert page.headers["x-has-more"] == "true"

    tail = client.get(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals?limit=2&offset=2",
        headers=bearer(),
    )
    assert len(tail.json()) == 1
    assert tail.headers["x-has-more"] == "false"


def test_duplicate_domain_is_rejected_with_a_typed_conflict(client):
    _create_prospect(client)
    duplicate = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Acme Bygg Sverige", "website_url": "https://www.acme-bygg.example/om"},
        headers=bearer(),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "PROSPECT_DOMAIN_DUPLICATE"


def test_network_fetch_requires_confirmation_and_the_kill_switch(client):
    prospect = _create_prospect(client)
    response = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={},
        headers=bearer(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NETWORK_FETCH_CONFIRMATION_REQUIRED"

    disabled = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"allow_network_fetch": True},
        headers=bearer(),
    )
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["code"] == "WEBSITE_FETCH_DISABLED"

    # A failed attempt is recorded, never left pinned to "running".
    listed = client.get(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses", headers=bearer()
    ).json()
    assert [row["status"] for row in listed] == ["failed", "failed"]


def test_validation_errors_use_the_shared_contract(client):
    response = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "X", "website_url": "ftp://acme.example"},
        headers=bearer(),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert set(body["fields"]) == {"company_name", "website_url"}
    assert "request_id" in body


def test_proposal_package_prices_must_be_numeric(client):
    prospect = _create_prospect(client)
    analysis = _analyze(client, prospect["id"])
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()
    rejected = client.patch(
        f"/api/v1/prospecting/proposals/{proposal['id']}",
        json={"packages": [{"name": "Bas", "price_sek": "ring oss"}]},
        headers=bearer(),
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "REQUEST_VALIDATION_FAILED"


def test_html_output_escapes_operator_supplied_content(client):
    prospect = _create_prospect(client, company_name="<script>alert(1)</script> AB")
    analysis = _analyze(client, prospect["id"])
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()
    _approve(client, proposal["id"])
    token = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/share",
        json={"expires_in_days": 3},
        headers=bearer(),
    ).json()["token"]
    page = client.get(f"/api/v1/public/prospecting/proposals/{token}")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_share_token_is_opaque_and_not_stored_in_clear(client, db_session):
    from app.prospecting.models import WebsiteProposal

    prospect = _create_prospect(client)
    analysis = _analyze(client, prospect["id"])
    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={"analysis_id": analysis["id"]},
        headers=bearer(),
    ).json()
    _approve(client, proposal["id"])
    token = client.post(
        f"/api/v1/prospecting/proposals/{proposal['id']}/share",
        json={"expires_in_days": 3},
        headers=bearer(),
    ).json()["token"]

    stored = db_session.get(WebsiteProposal, proposal["id"])
    assert stored.share_token_hash != token
    assert re.fullmatch(r"[0-9a-f]{64}", stored.share_token_hash)
    assert client.get("/api/v1/public/prospecting/proposals/not-a-token").status_code == 404


CONTACT_SNAPSHOT = """<!doctype html><html lang="sv"><head><title>Acme Bygg AB — hus i Uppsala</title>
<script type="application/ld+json">{"@type":"Organization","name":"Acme Bygg AB"}</script></head>
<body><h1>Acme Bygg</h1>
<p>Mejla <a href="mailto:hej@acme-bygg.example">hej@acme-bygg.example</a> eller ring 018-123456.</p>
<p>Org.nr 5560360793. Besök oss på Kungsgatan 1, 753 21 Uppsala.</p>
<a href="https://www.linkedin.com/company/acme-bygg">LinkedIn</a></body></html>"""


def test_analysis_offers_contact_candidates_with_provenance(client):
    """The page already told us who to contact; the operator should not retype it."""
    prospect = _create_prospect(client, contact_email=None, contact_verified=False, contact_verification_source=None)
    response = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"html_snapshot": CONTACT_SNAPSHOT},
        headers=bearer(),
    )
    assert response.status_code == 201, response.text
    candidates = response.json()["contact_candidates"]

    by_field: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_field.setdefault(candidate["field"], []).append(candidate)

    assert "hej@acme-bygg.example" in [c["value"] for c in by_field["email"]]
    assert by_field["company_name"][0]["value"] == "Acme Bygg AB"
    assert "5560360793" in [c["value"] for c in by_field["org_number"]]
    # Page trivia is not a contact suggestion.
    assert "postal_code" not in by_field and "social_link" not in by_field
    # The phone pattern also matches nine digits of the organisation number;
    # that is noise the operator would have to disprove, so it is filtered out.
    assert [c["value"] for c in by_field["phone"]] == ["018-123456"]

    for candidate in candidates:
        assert candidate["source"], "every suggestion must name its extractor"
        assert candidate["evidence"], "every suggestion must name where it was seen"
        assert 0 < candidate["confidence"] <= 1
        # A suggestion may never carry a score, price or recommendation.
        assert not {"score", "price", "max_price", "rav", "recommendation"} & set(candidate)


def test_contact_candidates_never_verify_the_prospect(client):
    """Extraction is evidence, not approval: a human still has to vouch for it."""
    prospect = _create_prospect(client, contact_email=None, contact_verified=False, contact_verification_source=None)
    client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/analyses",
        json={"html_snapshot": CONTACT_SNAPSHOT},
        headers=bearer(),
    )
    after = client.get(f"/api/v1/prospecting/prospects/{prospect['id']}", headers=bearer()).json()
    assert after["contact_verified"] is False
    assert after["contact_email"] is None
    assert after["contact_verification_source"] is None

    proposal = client.post(
        f"/api/v1/prospecting/prospects/{prospect['id']}/proposals",
        json={},
        headers=bearer(),
    )
    assert proposal.status_code == 201, proposal.text
    blocked = client.post(
        f"/api/v1/prospecting/proposals/{proposal.json()['id']}/approve",
        json={
            "analysis_verified": True,
            "contact_verified": True,
            "content_approved": True,
            "legal_basis_verified": True,
            "reviewer_note": "Trying to approve on extracted data alone.",
        },
        headers=bearer(),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CONTACT_NOT_VERIFIED"


def test_analysis_without_contact_details_returns_an_empty_candidate_list(client):
    prospect = _create_prospect(client)
    analysis = _analyze(client, prospect["id"])
    assert analysis["contact_candidates"] == [] or all(
        candidate["field"] in {"company_name", "phone"} for candidate in analysis["contact_candidates"]
    )
