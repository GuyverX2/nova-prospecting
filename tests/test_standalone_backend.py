from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.core.config import settings
from app.crm.client import SalesOSCrmClient
from app.db.session import Base, get_db
from app.main import app
from app.prospecting.schemas import ProspectCreate, ProspectPromoteRequest
from app.prospecting.service import ProspectingError, create_prospect, promote_prospect_to_crm
from app.prospecting.models import WebsiteProspect
from app.auth import PlatformPrincipal
from app.tenancy.service import TenantContext


@contextmanager
def workspace():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    principal = PlatformPrincipal("operator@acme.test", "tenant-acme", frozenset({"operator"}), frozenset({"nova:write"}), "caller-token")
    yield db, TenantContext(principal.tenant_id, principal.roles, principal.scopes), principal
    db.close()
    engine.dispose()


def test_unavailable_crm_leaves_prospect_unchanged(monkeypatch):
    with workspace() as (db, ctx, principal):
        prospect = create_prospect(
            db, ctx, principal,
            ProspectCreate(company_name="Acme AB", website_url="https://acme.example"),
        )
        monkeypatch.setattr(settings, "SALESOS_CRM_BASE_URL", "")
        try:
            promote_prospect_to_crm(
                db, ctx, principal, prospect["id"],
                ProspectPromoteRequest(vertical_id="web", brand_id="acme"),
            )
        except ProspectingError as exc:
            assert exc.code == "CRM_UNAVAILABLE"
        else:
            raise AssertionError("expected unavailable CRM")
        assert db.get(WebsiteProspect, prospect["id"]).status == "qualified"


def test_jwt_tenant_claim_is_required_and_cannot_be_overridden():
    with workspace() as (db, ctx, principal):
        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            missing_tenant = create_access_token({"sub": principal.sub, "roles": ["operator"], "scopes": ["nova:write"]})
            assert client.get("/api/v1/prospecting/summary", headers={"Authorization": f"Bearer {missing_tenant}"}).status_code == 401
            valid = create_access_token({"sub": principal.sub, "tenant_id": principal.tenant_id, "roles": ["operator"], "scopes": ["nova:write"]})
            assert client.get("/api/v1/prospecting/summary?tenant_id=other-tenant", headers={"Authorization": f"Bearer {valid}"}).status_code == 403
        finally:
            app.dependency_overrides.clear()


def test_crm_promotion_uses_a_stable_idempotency_key(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _):
            return b'{"customer_id":"c1","lead_id":"l1","case_id":"k1","crm_lead_path":"/leads/l1","crm_case_path":"/cases/k1"}'

    def fake_urlopen(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr("app.crm.client.urlopen", fake_urlopen)
    crm = SalesOSCrmClient("https://crm.example")
    for _ in range(2):
        result = crm.promote_prospect(bearer_token="caller-token", tenant_id="tenant-7", prospect_id="pr_123", payload={"company_name": "Acme"})
        assert result.lead_id == "l1"
    assert [request.get_header("Idempotency-key") for request in requests] == ["nova-prospect:tenant-7:pr_123"] * 2
    assert [request.get_header("Authorization") for request in requests] == ["Bearer caller-token"] * 2
    assert all(request.full_url.endswith("/api/v1/nova/prospects/promote") for request in requests)
