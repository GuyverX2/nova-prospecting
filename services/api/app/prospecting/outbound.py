"""Fail-closed prospecting email adapter with approval and opt-out support."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings

RESEND_ENDPOINT = "https://api.resend.com/emails"


class ProspectingDeliveryError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 422):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class DeliveryReceipt:
    provider: str
    delivery_id: str
    external_sent: bool


def opt_out_token(tenant_id: int, prospect_id: str, email: str) -> str:
    message = f"{tenant_id}:{prospect_id}:{email.strip().lower()}".encode("utf-8")
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_opt_out_token(token: str, tenant_id: int, prospect_id: str, email: str) -> bool:
    return hmac.compare_digest(token, opt_out_token(tenant_id, prospect_id, email))


def deliver_email(
    *,
    provider: str,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    unsubscribe_url: str,
    idempotency_key: str | None = None,
) -> DeliveryReceipt:
    if provider == "queue":
        return DeliveryReceipt(provider="queue", delivery_id=f"queued_{uuid.uuid4().hex[:16]}", external_sent=False)
    if provider == "mock":
        return DeliveryReceipt(provider="mock", delivery_id=f"mock_{uuid.uuid4().hex[:16]}", external_sent=False)
    if provider != "resend":
        raise ProspectingDeliveryError("EMAIL_PROVIDER_UNSUPPORTED", f"Unsupported email provider: {provider}")
    if not settings.PROSPECTING_REAL_EMAIL_ENABLED:
        raise ProspectingDeliveryError("REAL_EMAIL_DISABLED", "Real prospecting email is disabled by the operator kill switch", 409)
    if settings.PROSPECTING_EMAIL_PROVIDER != "resend":
        raise ProspectingDeliveryError("EMAIL_PROVIDER_NOT_ALLOWED", "Resend is not the configured prospecting provider", 409)
    if not settings.PROSPECTING_EMAIL_API_KEY or not settings.PROSPECTING_EMAIL_FROM:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_NOT_CONFIGURED", "Email API key and verified sender are required", 409)
    payload = {
        "from": settings.PROSPECTING_EMAIL_FROM,
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
    request_headers = {
        "Authorization": f"Bearer {settings.PROSPECTING_EMAIL_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "SalesOS-Prospecting/1.0",
    }
    if idempotency_key:
        # Resend retains idempotency keys, so a lost response can be retried
        # without creating a second external message for the same proposal.
        request_headers["Idempotency-Key"] = idempotency_key[:256]
    request = Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=request_headers,
    )
    try:
        with urlopen(request, timeout=12) as response:
            response_payload = json.loads(response.read(256_000).decode("utf-8"))
    except HTTPError as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_REJECTED", f"Email provider returned HTTP {exc.code}", 502) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_UNAVAILABLE", "Email provider could not be reached", 502) from exc
    delivery_id = str(response_payload.get("id") or "").strip()
    if not delivery_id:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_INVALID_RESPONSE", "Email provider response had no delivery id", 502)
    return DeliveryReceipt(provider="resend", delivery_id=delivery_id, external_sent=True)
