"""Environment-only configuration for the standalone Nova service."""
from __future__ import annotations

import os


class Settings:
    DATABASE_URL = os.getenv("NOVA_DATABASE_URL", "sqlite:///./nova.db")
    JWT_SECRET = os.getenv("NOVA_JWT_SECRET", "nova-development-secret-change-me-32b")
    JWT_AUDIENCE = os.getenv("NOVA_JWT_AUDIENCE", "nova")
    SALESOS_CRM_BASE_URL = os.getenv("SALESOS_CRM_BASE_URL", "")
    SALESOS_CRM_TIMEOUT_SECONDS = float(os.getenv("SALESOS_CRM_TIMEOUT_SECONDS", "5"))
    PROSPECTING_FETCH_ENABLED = os.getenv("PROSPECTING_FETCH_ENABLED", "false").lower() == "true"
    PROSPECTING_PUBLIC_BASE_URL = os.getenv("PROSPECTING_PUBLIC_BASE_URL", "http://localhost:8000")
    PROSPECTING_DISCOVERY_PROVIDER = os.getenv("PROSPECTING_DISCOVERY_PROVIDER", "manual")
    PROSPECTING_REAL_EMAIL_ENABLED = os.getenv("PROSPECTING_REAL_EMAIL_ENABLED", "false").lower() == "true"
    PROSPECTING_EMAIL_PROVIDER = os.getenv("PROSPECTING_EMAIL_PROVIDER", "queue")
    PROSPECTING_EMAIL_API_KEY = os.getenv("PROSPECTING_EMAIL_API_KEY", "")
    PROSPECTING_EMAIL_FROM = os.getenv("PROSPECTING_EMAIL_FROM", "")
    PROSPECTING_SMTP_HOST = os.getenv("PROSPECTING_SMTP_HOST", "")
    PROSPECTING_SMTP_PORT = int(os.getenv("PROSPECTING_SMTP_PORT", "587"))
    PROSPECTING_SMTP_STARTTLS = os.getenv("PROSPECTING_SMTP_STARTTLS", "true").lower() == "true"
    PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", "")
    GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
    AGENT_SCHEDULER_ENABLED = False

    def prospecting_smtp_mailboxes(self) -> list[tuple[str, str]]:
        address = os.getenv("PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "").strip()
        password = os.getenv("PROSPECTING_SMTP_MAILBOX_1_PASSWORD", "")
        return [(address, password)] if address and password else []

    def prospecting_smtp_from_addresses(self) -> list[str]:
        return [address for address, _ in self.prospecting_smtp_mailboxes()]

    def prospecting_email_configured(self) -> bool:
        return bool(self.PROSPECTING_EMAIL_FROM or self.prospecting_smtp_mailboxes())


settings = Settings()
