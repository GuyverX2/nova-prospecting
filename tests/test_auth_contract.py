"""Authentication and authorization contract for the platform-issued JWT."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import TENANT_A, bearer

from app.core.config import settings


def _token(claims: dict, *, secret: str | None = None, audience: str | None = "__default__") -> str:
    payload = {
        "sub": "operator@acme.test",
        "tenant_id": TENANT_A,
        "roles": ["operator"],
        "scopes": ["nova:write"],
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    if audience == "__default__":
        payload["aud"] = settings.JWT_AUDIENCE
    elif audience is not None:
        payload["aud"] = audience
    payload.update(claims)
    return jwt.encode(payload, secret or settings.JWT_SECRET, algorithm="HS256")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("name", "headers"),
    [
        ("no header", {}),
        ("empty bearer", {"Authorization": "Bearer "}),
        ("wrong scheme", {"Authorization": "Basic b3BlcmF0b3I6cw=="}),
        ("garbage token", {"Authorization": "Bearer not-a-jwt"}),
    ],
)
def test_requests_without_a_usable_token_are_rejected(client, name, headers):
    response = client.get("/api/v1/prospecting/summary", headers=headers)
    assert response.status_code == 401, name
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize(
    ("name", "token_kwargs"),
    [
        ("foreign signing key", {"secret": "an-entirely-different-secret-value-32"}),
        ("wrong audience", {"audience": "some-other-service"}),
        ("missing audience", {"audience": None}),
    ],
)
def test_tokens_signed_or_scoped_for_something_else_are_rejected(client, name, token_kwargs):
    response = client.get("/api/v1/prospecting/summary", headers=_auth(_token({}, **token_kwargs)))
    assert response.status_code == 401, name


def test_expired_tokens_are_rejected(client):
    expired = jwt.encode(
        {
            "sub": "operator@acme.test",
            "tenant_id": TENANT_A,
            "roles": ["operator"],
            "scopes": ["nova:write"],
            "aud": settings.JWT_AUDIENCE,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    assert client.get("/api/v1/prospecting/summary", headers=_auth(expired)).status_code == 401


def test_tokens_without_an_expiry_are_rejected(client):
    """An eternal token is a credential that can never be revoked."""
    eternal = jwt.encode(
        {
            "sub": "operator@acme.test",
            "tenant_id": TENANT_A,
            "roles": ["operator"],
            "scopes": ["nova:write"],
            "aud": settings.JWT_AUDIENCE,
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    assert client.get("/api/v1/prospecting/summary", headers=_auth(eternal)).status_code == 401


def test_unsigned_tokens_are_rejected(client):
    """alg=none must never be accepted as a valid signature."""
    unsigned = jwt.encode(
        {
            "sub": "operator@acme.test",
            "tenant_id": TENANT_A,
            "roles": ["operator"],
            "scopes": ["nova:write"],
            "aud": settings.JWT_AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )
    assert client.get("/api/v1/prospecting/summary", headers=_auth(unsigned)).status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"tenant_id": ""},
        {"tenant_id": "   "},
        {"tenant_id": 12345},
        {"roles": "operator"},
        {"scopes": {"nova:write": True}},
        {"roles": ["operator", 7]},
        {"sub": ""},
    ],
)
def test_malformed_identity_claims_are_rejected(client, claims):
    response = client.get("/api/v1/prospecting/summary", headers=_auth(_token(claims)))
    assert response.status_code == 401


def test_tenant_id_claim_is_required(client):
    payload = {
        "sub": "operator@acme.test",
        "roles": ["operator"],
        "scopes": ["nova:write"],
        "aud": settings.JWT_AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/v1/prospecting/summary", headers=_auth(token)).status_code == 401


def test_read_only_principals_cannot_mutate(client):
    """Reading is allowed without nova:write; writing is not."""
    read_only = bearer(scopes=["nova:read"], roles=["viewer"])
    assert client.get("/api/v1/prospecting/summary", headers=read_only).status_code == 200
    denied = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Acme AB", "website_url": "https://acme.example"},
        headers=read_only,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "PROSPECTING_WRITE_FORBIDDEN"


def test_admin_role_grants_write_without_an_explicit_scope(client):
    admin = bearer(roles=["platform_admin"], scopes=[])
    created = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Acme AB", "website_url": "https://acme.example"},
        headers=admin,
    )
    assert created.status_code == 201


def test_error_responses_never_echo_the_token(client):
    token = _token({})
    response = client.get("/api/v1/prospecting/nope", headers=_auth(token))
    assert response.status_code == 404
    assert token not in response.text
