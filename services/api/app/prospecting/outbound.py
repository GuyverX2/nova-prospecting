"""Fail-closed prospecting email adapter with approval and opt-out support."""
from __future__ import annotations

import hashlib
import hmac
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings
from app.integrations.http import (
    IntegrationRejected,
    IntegrationUnavailable,
    RetryPolicy,
    request_json,
)

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


def opt_out_token(tenant_id: str, prospect_id: str, email: str) -> str:
    message = f"{tenant_id}:{prospect_id}:{email.strip().lower()}".encode()
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_opt_out_token(token: str, tenant_id: str, prospect_id: str, email: str) -> bool:
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
    from_address: str | None = None,
) -> DeliveryReceipt:
    if provider == "queue":
        return DeliveryReceipt(provider="queue", delivery_id=f"queued_{uuid.uuid4().hex[:16]}", external_sent=False)
    if provider == "mock":
        return DeliveryReceipt(provider="mock", delivery_id=f"mock_{uuid.uuid4().hex[:16]}", external_sent=False)
    if provider == "smtp_generic":
        return _deliver_smtp_generic(
            recipient=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            unsubscribe_url=unsubscribe_url,
            from_address=from_address,
        )
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
        "User-Agent": "Nova-Prospecting/1.0",
    }
    if idempotency_key:
        # Resend retains idempotency keys, so a lost response can be retried
        # without creating a second external message for the same proposal.
        request_headers["Idempotency-Key"] = idempotency_key[:256]
    try:
        response_payload = request_json(
            RESEND_ENDPOINT,
            method="POST",
            json_body=payload,
            headers=request_headers,
            timeout=12,
            max_bytes=256_000,
            retry=RetryPolicy(attempts=2) if idempotency_key else None,
            provider="Email provider",
        )
    except IntegrationRejected as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_REJECTED", str(exc), 502) from exc
    except IntegrationUnavailable as exc:
        raise ProspectingDeliveryError(
            "EMAIL_PROVIDER_UNAVAILABLE", "Email provider could not be reached", 502
        ) from exc
    delivery_id = str(response_payload.get("id") or "").strip()
    if not delivery_id:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_INVALID_RESPONSE", "Email provider response had no delivery id", 502)
    return DeliveryReceipt(provider="resend", delivery_id=delivery_id, external_sent=True)


def _deliver_smtp_generic(
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    unsubscribe_url: str,
    from_address: str | None,
) -> DeliveryReceipt:
    if not settings.PROSPECTING_REAL_EMAIL_ENABLED:
        raise ProspectingDeliveryError("REAL_EMAIL_DISABLED", "Real prospecting email is disabled by the operator kill switch", 409)
    if settings.PROSPECTING_EMAIL_PROVIDER != "smtp_generic":
        raise ProspectingDeliveryError("EMAIL_PROVIDER_NOT_ALLOWED", "smtp_generic is not the configured prospecting provider", 409)
    if not settings.SMTP_MAILBOXES:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_NOT_CONFIGURED", "SMTP host and at least one mailbox are required", 409)
    mailbox = settings.smtp_mailbox(from_address)
    if mailbox is None:
        # Sending as an arbitrary address is how a service becomes a spam relay.
        raise ProspectingDeliveryError("EMAIL_FROM_NOT_ALLOWED", "From address is not in the smtp_generic allowlist", 409)
    sender = mailbox.from_address
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(
            mailbox.host, mailbox.port, timeout=settings.PROSPECTING_SMTP_TIMEOUT_SECONDS
        ) as client:
            if mailbox.starttls:
                client.starttls()
            client.login(mailbox.username, mailbox.password)
            client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_REJECTED", "SMTP authentication failed", 502) from exc
    except smtplib.SMTPException as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_REJECTED", "SMTP provider rejected the message", 502) from exc
    except (TimeoutError, OSError) as exc:
        raise ProspectingDeliveryError("EMAIL_PROVIDER_UNAVAILABLE", "SMTP provider could not be reached", 502) from exc
    return DeliveryReceipt(provider="smtp_generic", delivery_id=f"smtp_{uuid.uuid4().hex[:16]}", external_sent=True)
