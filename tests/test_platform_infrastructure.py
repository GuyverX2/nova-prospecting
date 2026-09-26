"""Cross-cutting infrastructure: HTTP client, rate limiting, logging, health."""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError

import pytest
from conftest import TENANT_A, TENANT_B, bearer

from app.core import logging as nova_logging
from app.core.ratelimit import FixedWindowRateLimiter, RateLimitExceeded
from app.integrations.http import (
    IntegrationRejected,
    IntegrationUnavailable,
    RetryPolicy,
    request_json,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self, size: int) -> bytes:
        return self._payload[:size]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info) -> None:
        return None


def _urlopen_returning(payload: dict, recorder: list | None = None):
    def _urlopen(request, timeout=None):
        if recorder is not None:
            recorder.append((request, timeout))
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    return _urlopen


# --------------------------------------------------------------------------- #
# Outbound HTTP
# --------------------------------------------------------------------------- #


def test_request_json_sends_a_bounded_json_request(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "app.integrations.http.urlopen", _urlopen_returning({"id": "abc"}, calls)
    )
    body = request_json(
        "https://provider.example/send",
        method="POST",
        json_body={"to": "anna@example"},
        headers={"Authorization": "Bearer secret-token"},
        timeout=3.5,
        provider="Test provider",
    )
    assert body == {"id": "abc"}
    request, timeout = calls[0]
    assert timeout == 3.5
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data) == {"to": "anna@example"}


def test_oversized_responses_are_refused(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.http.urlopen", _urlopen_returning({"pad": "x" * 5000})
    )
    with pytest.raises(IntegrationUnavailable):
        request_json("https://provider.example", max_bytes=100, provider="Test provider")


def test_error_statuses_never_leak_the_provider_body(monkeypatch):
    def _urlopen(request, timeout=None):
        raise HTTPError(
            "https://provider.example",
            401,
            "Unauthorized",
            {},
            None,
        )

    monkeypatch.setattr("app.integrations.http.urlopen", _urlopen)
    with pytest.raises(IntegrationRejected) as exc:
        request_json("https://provider.example", provider="Test provider")
    assert str(exc.value) == "Test provider returned HTTP 401"
    assert exc.value.status_code == 401


def test_transport_failures_are_retried_with_backoff(monkeypatch):
    attempts: list[int] = []
    sleeps: list[float] = []

    def _urlopen(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("connection refused")
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr("app.integrations.http.urlopen", _urlopen)
    body = request_json(
        "https://provider.example",
        retry=RetryPolicy(attempts=3, backoff_seconds=0.1),
        provider="Test provider",
        sleep=sleeps.append,
    )
    assert body == {"ok": True}
    assert len(attempts) == 3
    assert sleeps == [0.1, 0.2]


def test_client_errors_are_not_retried(monkeypatch):
    attempts: list[int] = []

    def _urlopen(request, timeout=None):
        attempts.append(1)
        raise HTTPError("https://provider.example", 422, "Unprocessable", {}, None)

    monkeypatch.setattr("app.integrations.http.urlopen", _urlopen)
    with pytest.raises(IntegrationRejected):
        request_json(
            "https://provider.example",
            retry=RetryPolicy(attempts=4, backoff_seconds=0),
            provider="Test provider",
            sleep=lambda _seconds: None,
        )
    assert len(attempts) == 1


def test_retries_stop_at_the_configured_attempt_count(monkeypatch):
    attempts: list[int] = []

    def _urlopen(request, timeout=None):
        attempts.append(1)
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.integrations.http.urlopen", _urlopen)
    with pytest.raises(IntegrationUnavailable):
        request_json(
            "https://provider.example",
            retry=RetryPolicy(attempts=3, backoff_seconds=0),
            provider="Test provider",
            sleep=lambda _seconds: None,
        )
    assert len(attempts) == 3


def test_unparsable_bodies_are_reported_as_unavailable(monkeypatch):
    def _urlopen(request, timeout=None):
        return _FakeResponse(b"<html>gateway error</html>")

    monkeypatch.setattr("app.integrations.http.urlopen", _urlopen)
    with pytest.raises(IntegrationUnavailable):
        request_json("https://provider.example", provider="Test provider")


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


def test_rate_limiter_counts_per_key_and_window():
    clock = [1000.0]
    limiter = FixedWindowRateLimiter(window_seconds=60, clock=lambda: clock[0])
    for _ in range(3):
        limiter.check("analysis", "tenant-a", 3)
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check("analysis", "tenant-a", 3)
    assert exc.value.retry_after_seconds > 0
    # Another tenant and another action are unaffected.
    limiter.check("analysis", "tenant-b", 3)
    limiter.check("delivery", "tenant-a", 3)
    # The window rolls over.
    clock[0] += 61
    limiter.check("analysis", "tenant-a", 3)


def test_a_limit_of_zero_disables_the_check():
    limiter = FixedWindowRateLimiter()
    for _ in range(100):
        limiter.check("analysis", "tenant-a", 0)


def test_analysis_endpoint_is_rate_limited_per_tenant(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PROSPECTING_ANALYSIS_RATE_LIMIT_PER_MINUTE", 2)
    prospect = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Acme AB", "website_url": "https://acme.example"},
        headers=bearer(TENANT_A),
    ).json()
    snapshot = {"html_snapshot": "<html><head><title>A</title></head><body>x</body></html>"}
    url = f"/api/v1/prospecting/prospects/{prospect['id']}/analyses"
    assert client.post(url, json=snapshot, headers=bearer(TENANT_A)).status_code == 201
    assert client.post(url, json=snapshot, headers=bearer(TENANT_A)).status_code == 201
    throttled = client.post(url, json=snapshot, headers=bearer(TENANT_A))
    assert throttled.status_code == 429
    assert throttled.json()["detail"]["code"] == "RATE_LIMITED"
    assert int(throttled.headers["retry-after"]) > 0

    # A different tenant still has its own budget.
    other = client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Globex AB", "website_url": "https://globex.example"},
        headers=bearer(TENANT_B, subject="operator@globex.test"),
    ).json()
    assert (
        client.post(
            f"/api/v1/prospecting/prospects/{other['id']}/analyses",
            json=snapshot,
            headers=bearer(TENANT_B, subject="operator@globex.test"),
        ).status_code
        == 201
    )


# --------------------------------------------------------------------------- #
# Logging and correlation
# --------------------------------------------------------------------------- #


def test_logs_are_single_line_json_with_the_request_id():
    formatter = nova_logging.JsonFormatter()
    nova_logging.set_request_id("req-42")
    try:
        record = logging.LogRecord(
            "nova.test", logging.INFO, __file__, 10, "hello %s", ("world",), None
        )
        record.tenant_id = "tenant-acme"
        rendered = formatter.format(record)
    finally:
        nova_logging.reset_request_id()
    assert "\n" not in rendered
    payload = json.loads(rendered)
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-42"
    assert payload["tenant_id"] == "tenant-acme"


def test_exception_logs_include_the_traceback():
    formatter = nova_logging.JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "nova.test", logging.ERROR, __file__, 10, "failed", (), __import__("sys").exc_info()
        )
    payload = json.loads(formatter.format(record))
    assert "ValueError: boom" in payload["exception"]
    assert "\n" not in formatter.format(record)


def test_incoming_request_ids_are_sanitized_before_use():
    assert nova_logging.sanitize_request_id("abc-123_XYZ") == "abc-123_XYZ"
    # A client-supplied id can never inject a second log line.
    assert "\n" not in nova_logging.sanitize_request_id("evil\ninjected")
    # Missing or unusable ids fall back to a generated one rather than being empty.
    assert len(nova_logging.sanitize_request_id("")) == 32
    assert len(nova_logging.sanitize_request_id("\n\r")) == 32
    assert len(nova_logging.sanitize_request_id("x" * 500)) == nova_logging.MAX_REQUEST_ID_LENGTH


def test_request_id_round_trips_through_the_api(client):
    response = client.get(
        "/api/v1/prospecting/summary",
        headers={**bearer(), "X-Request-ID": "trace-abc-1"},
    )
    assert response.headers["x-request-id"] == "trace-abc-1"

    generated = client.get("/api/v1/prospecting/summary", headers=bearer())
    assert len(generated.headers["x-request-id"]) >= 16


def test_audit_events_record_the_request_id(client, db_session):
    from app.tenancy.service import AuditEvent

    client.post(
        "/api/v1/prospecting/prospects",
        json={"company_name": "Acme AB", "website_url": "https://acme.example"},
        headers={**bearer(), "X-Request-ID": "trace-audit-1"},
    )
    event = db_session.query(AuditEvent).one()
    assert event.tenant_id == TENANT_A
    assert event.action_type == "prospecting.prospect_created"
    assert event.request_id == "trace-audit-1"
    assert event.actor_subject == "operator@acme.test"
    assert event.created_at is not None


def test_audit_payloads_are_capped(db_session):
    from app.tenancy.service import MAX_AUDIT_PAYLOAD_CHARS, AuditEvent, record_audit

    record_audit(
        db_session,
        tenant_id=TENANT_A,
        actor_subject="operator@acme.test",
        action_type="prospecting.test",
        target_type="website_prospect",
        target_id="pr_1",
        request_id=None,
        after={"blob": "x" * 50_000},
    )
    db_session.commit()
    event = db_session.query(AuditEvent).one()
    assert len(event.after_json) <= MAX_AUDIT_PAYLOAD_CHARS


# --------------------------------------------------------------------------- #
# Health and metrics
# --------------------------------------------------------------------------- #


def test_liveness_does_not_depend_on_the_database(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_the_database_and_configuration(client):
    body = client.get("/health/ready").json()
    assert body["status"] == "ready"
    assert body["checks"] == {"config": "ok", "database": "ok"}
    assert "warnings" in body


def test_readiness_fails_when_the_database_is_gone(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def _broken_connect():
        raise OperationalError("SELECT 1", {}, Exception("no database"))

    monkeypatch.setattr("app.main.engine.connect", _broken_connect)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"


def test_metrics_expose_request_counters_without_tenant_labels(client):
    client.get("/api/v1/prospecting/summary", headers=bearer())
    body = client.get("/metrics").text
    assert 'nova_http_requests_total{method="GET",route="/prospecting/summary",status="2xx"}' in body
    assert TENANT_A not in body


def test_unknown_api_routes_stay_json(client):
    response = client.get("/api/v1/does-not-exist", headers=bearer())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ROUTE_NOT_FOUND"
