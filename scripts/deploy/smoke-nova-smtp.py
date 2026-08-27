#!/usr/bin/env python3
"""Verify Nova smtp_generic credentials (login only unless --send-test-to is set)."""
from __future__ import annotations

import argparse
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402


def verify_login(address: str, password: str) -> None:
    with smtplib.SMTP(settings.PROSPECTING_SMTP_HOST, settings.PROSPECTING_SMTP_PORT, timeout=20) as client:
        if settings.PROSPECTING_SMTP_STARTTLS:
            client.starttls()
        client.login(address, password)


def send_test(address: str, password: str, recipient: str) -> None:
    message = EmailMessage()
    message["From"] = address
    message["To"] = recipient
    message["Subject"] = "SalesOS Nova SMTP smoke test"
    message.set_content(
        "This is an operator smoke test from scripts/deploy/smoke-nova-smtp.py. "
        "Safe to delete."
    )
    with smtplib.SMTP(settings.PROSPECTING_SMTP_HOST, settings.PROSPECTING_SMTP_PORT, timeout=20) as client:
        if settings.PROSPECTING_SMTP_STARTTLS:
            client.starttls()
        client.login(address, password)
        client.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--send-test-to",
        metavar="EMAIL",
        help="Send one test message from the first mailbox to this address",
    )
    args = parser.parse_args()

    if settings.PROSPECTING_EMAIL_PROVIDER != "smtp_generic":
        raise SystemExit("PROSPECTING_EMAIL_PROVIDER must be smtp_generic")
    if not settings.PROSPECTING_REAL_EMAIL_ENABLED:
        raise SystemExit("PROSPECTING_REAL_EMAIL_ENABLED must be true for SMTP smoke")
    if not settings.prospecting_email_configured():
        raise SystemExit("SMTP host and at least one mailbox with password are required")

    mailboxes = settings.prospecting_smtp_mailboxes()
    for address, password in mailboxes:
        try:
            verify_login(address, password)
        except smtplib.SMTPAuthenticationError as exc:
            hint = ""
            if "gmail" not in (settings.PROSPECTING_SMTP_HOST or "").lower():
                hint = (
                    " Hint: triplusmedia.com MX is Google Workspace — "
                    "set PROSPECTING_SMTP_HOST=smtp.gmail.com (App Password if 2FA)."
                )
            elif exc.smtp_code == 535:
                hint = " Hint: Google often requires an App Password when 2FA is enabled."
            raise SystemExit(
                f"SMTP authentication failed for {address} "
                f"(smtp_code={exc.smtp_code}).{hint}"
            ) from exc
        except smtplib.SMTPException as exc:
            raise SystemExit(f"SMTP error for {address}: {exc}") from exc
        except OSError as exc:
            raise SystemExit(f"Could not reach {settings.PROSPECTING_SMTP_HOST}: {exc}") from exc
        print(f"OK login: {address}")

    print(
        "Nova SMTP smoke passed "
        f"({len(mailboxes)} mailbox(es), host={settings.PROSPECTING_SMTP_HOST}:{settings.PROSPECTING_SMTP_PORT})"
    )

    if args.send_test_to:
        first_address, first_password = mailboxes[0]
        send_test(first_address, first_password, args.send_test_to.strip())
        print(f"Sent test message from {first_address} to {args.send_test_to.strip()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
