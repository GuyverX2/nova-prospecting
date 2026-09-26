#!/usr/bin/env python3
"""Smoke-send one Nova Resend message (no password print)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[2] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="Test recipient (operator inbox)")
    args = parser.parse_args()

    if settings.PROSPECTING_EMAIL_PROVIDER != "resend":
        raise SystemExit("PROSPECTING_EMAIL_PROVIDER must be resend")
    if not settings.PROSPECTING_REAL_EMAIL_ENABLED:
        raise SystemExit("PROSPECTING_REAL_EMAIL_ENABLED must be true")
    if not settings.PROSPECTING_EMAIL_API_KEY or not settings.PROSPECTING_EMAIL_FROM:
        raise SystemExit("Resend API key and FROM are required")

    payload = {
        "from": settings.PROSPECTING_EMAIL_FROM,
        "to": [args.to.strip()],
        "subject": "SalesOS Nova Resend smoke test",
        "text": "Operator smoke from scripts/deploy/smoke-nova-resend.py. Safe to delete.",
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.PROSPECTING_EMAIL_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "SalesOS-Nova-Smoke/1.0",
        },
    )
    try:
        # S310: RESEND_ENDPOINT is a fixed https constant in this script.
        with urlopen(request, timeout=20) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"Resend HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Resend unreachable: {exc}") from exc

    email_id = body.get("id") or "?"
    print(
        f"OK resent smoke from={settings.PROSPECTING_EMAIL_FROM} "
        f"to={args.to.strip()} id={email_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
