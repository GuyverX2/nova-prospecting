"""Shared fixtures: an isolated database, an API client, and token minting."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import PlatformPrincipal, create_access_token
from app.core.ratelimit import limiter
from app.db.session import Base, get_db
from app.main import app
from app.tenancy.service import TenantContext

TENANT_A = "tenant-acme"
TENANT_B = "tenant-globex"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """A private in-memory database per test, created from the live models."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


def make_principal(
    tenant_id: str = TENANT_A,
    *,
    subject: str = "operator@acme.test",
    roles: frozenset[str] = frozenset({"operator"}),
    scopes: frozenset[str] = frozenset({"nova:write"}),
) -> PlatformPrincipal:
    return PlatformPrincipal(subject, tenant_id, roles, scopes, "caller-token")


def make_context(principal: PlatformPrincipal) -> TenantContext:
    return TenantContext(principal.tenant_id, principal.roles, principal.scopes)


def bearer(
    tenant_id: str = TENANT_A,
    *,
    subject: str = "operator@acme.test",
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": subject,
            "tenant_id": tenant_id,
            "roles": roles if roles is not None else ["operator"],
            "scopes": scopes if scopes is not None else ["nova:write"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def principal() -> PlatformPrincipal:
    return make_principal()


@pytest.fixture()
def ctx(principal: PlatformPrincipal) -> TenantContext:
    return make_context(principal)


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    """API client bound to the test database, with startup/shutdown executed."""

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
