"""Environment-only configuration for the standalone Nova service.

One module owns every runtime setting. Values are read from the environment
once at import, validated explicitly, and exposed through the ``settings``
singleton. Unsafe combinations (a default JWT secret in production, real email
without a configured provider, ...) fail closed at startup instead of degrading
silently at request time.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEV_JWT_SECRET = "nova-development-secret-change-me-32b"  # noqa: S105 - documented dev-only default
MIN_JWT_SECRET_LENGTH = 32

ENVIRONMENTS = ("development", "test", "production")
DISCOVERY_PROVIDERS = ("manual", "google_places", "disabled")
EMAIL_PROVIDERS = ("queue", "mock", "resend", "smtp_generic", "disabled")
EXTERNAL_EMAIL_PROVIDERS = ("resend", "smtp_generic")

#: Highest mailbox index read from the environment for ``smtp_generic``.
MAX_SMTP_MAILBOXES = 8


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a safe runtime configuration."""


class _Env:
    """Reader over an environment mapping, so configuration is testable."""

    def __init__(self, source: Mapping[str, str]):
        self._source = source

    def raw(self, name: str, default: str = "") -> str:
        """Value as provided - used for secrets, where whitespace is meaningful."""
        value = self._source.get(name)
        return default if value is None else value

    def text(self, name: str, default: str = "") -> str:
        value = self._source.get(name)
        if value is None:
            return default
        value = value.strip()
        return value or default

    def flag(self, name: str, default: bool) -> bool:
        raw = self.text(name)
        if not raw:
            return default
        lowered = raw.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ConfigError(f"{name} must be a boolean (true/false)")

    def integer(
        self, name: str, default: int, *, minimum: int | None = None, maximum: int | None = None
    ) -> int:
        raw = self.text(name)
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer") from exc
        if minimum is not None and value < minimum:
            raise ConfigError(f"{name} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise ConfigError(f"{name} must be <= {maximum}")
        return value

    def number(self, name: str, default: float, *, minimum: float = 0.0) -> float:
        raw = self.text(name)
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number") from exc
        if value <= minimum:
            raise ConfigError(f"{name} must be greater than {minimum}")
        return value


@dataclass(frozen=True)
class SmtpMailbox:
    """One allowlisted sending identity for the ``smtp_generic`` provider."""

    host: str
    port: int
    username: str
    password: str
    from_address: str
    starttls: bool

    @property
    def is_complete(self) -> bool:
        return bool(self.host and self.username and self.password and self.from_address)


def _smtp_mailboxes(env: _Env) -> tuple[SmtpMailbox, ...]:
    """Read the documented PROSPECTING_SMTP_MAILBOX_<n>_{ADDRESS,PASSWORD} pairs.

    All mailboxes share one relay (PROSPECTING_SMTP_HOST/PORT/STARTTLS); the
    address doubles as the SMTP username, which is how the deployed Google
    Workspace relay is configured. A half-configured mailbox is a hard error:
    silently dropping it would send from the wrong identity.
    """
    host = env.text("PROSPECTING_SMTP_HOST")
    port = env.integer("PROSPECTING_SMTP_PORT", 587, minimum=1, maximum=65535)
    starttls = env.flag("PROSPECTING_SMTP_STARTTLS", True)
    mailboxes: list[SmtpMailbox] = []
    incomplete: list[str] = []
    for index in range(1, MAX_SMTP_MAILBOXES + 1):
        prefix = f"PROSPECTING_SMTP_MAILBOX_{index}_"
        address = env.text(f"{prefix}ADDRESS").lower()
        password = env.raw(f"{prefix}PASSWORD")
        if not address and not password:
            continue
        if not address or not password:
            incomplete.append(f"{prefix}ADDRESS/{prefix}PASSWORD")
            continue
        mailboxes.append(
            SmtpMailbox(
                host=host,
                port=port,
                username=address,
                password=password,
                from_address=address,
                starttls=starttls,
            )
        )
    if incomplete:
        raise ConfigError(
            "Incomplete SMTP mailbox configuration (address and password are both required): "
            + ", ".join(incomplete)
        )
    if mailboxes and not host:
        raise ConfigError("PROSPECTING_SMTP_HOST is required when SMTP mailboxes are configured")
    return tuple(mailboxes)


@dataclass
class Settings:
    """Runtime configuration. Mutable so tests can override a single value."""

    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    DATABASE_URL: str = "sqlite:///./nova.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_AUTO_CREATE: bool = True
    # Secrets are excluded from repr(): a dataclass dump must never be able to
    # leak a credential into a log line or a traceback.
    JWT_SECRET: str = field(default=DEV_JWT_SECRET, repr=False)
    JWT_AUDIENCE: str = "nova"
    JWT_LEEWAY_SECONDS: int = 10
    CORS_ALLOW_ORIGINS: tuple[str, ...] = ()
    SPA_DIST_DIR: str = "apps/nova/dist"
    SALESOS_CRM_BASE_URL: str = ""
    SALESOS_CRM_TIMEOUT_SECONDS: float = 5.0
    PROSPECTING_FETCH_ENABLED: bool = False
    PROSPECTING_PUBLIC_BASE_URL: str = "http://localhost:8000"
    PROSPECTING_DISCOVERY_PROVIDER: str = "manual"
    PROSPECTING_REAL_EMAIL_ENABLED: bool = False
    PROSPECTING_EMAIL_PROVIDER: str = "queue"
    PROSPECTING_EMAIL_API_KEY: str = field(default="", repr=False)
    PROSPECTING_EMAIL_FROM: str = ""
    PROSPECTING_SMTP_HOST: str = ""
    PROSPECTING_SMTP_PORT: int = 587
    PROSPECTING_SMTP_STARTTLS: bool = True
    PROSPECTING_SMTP_TIMEOUT_SECONDS: float = 20.0
    PROSPECTING_ANALYSIS_RATE_LIMIT_PER_MINUTE: int = 20
    PROSPECTING_DISCOVERY_RATE_LIMIT_PER_MINUTE: int = 10
    PROSPECTING_DELIVERY_RATE_LIMIT_PER_MINUTE: int = 30
    PAGESPEED_API_KEY: str = field(default="", repr=False)
    PAGESPEED_TIMEOUT_SECONDS: float = 25.0
    GOOGLE_PLACES_API_KEY: str = field(default="", repr=False)
    #: Background execution is not part of this service; the flag stays visible
    #: in the policy contract so operators can see that nothing runs unattended.
    AGENT_SCHEDULER_ENABLED: bool = False
    #: Allowlisted sending identities for ``smtp_generic``; never logged.
    SMTP_MAILBOXES: tuple[SmtpMailbox, ...] = field(default_factory=tuple, repr=False)

    # -- construction ----------------------------------------------------- #

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``environ`` (defaults to the process environment)."""
        env = _Env(os.environ if environ is None else environ)
        name = (env.text("NOVA_ENV", "development")).lower()
        return cls(
            ENV=name,
            LOG_LEVEL=env.text("NOVA_LOG_LEVEL", "INFO").upper(),
            LOG_FORMAT=env.text("NOVA_LOG_FORMAT", "json").lower(),
            DATABASE_URL=env.text("NOVA_DATABASE_URL", "sqlite:///./nova.db"),
            DB_POOL_SIZE=env.integer("NOVA_DB_POOL_SIZE", 5, minimum=1, maximum=100),
            DB_MAX_OVERFLOW=env.integer("NOVA_DB_MAX_OVERFLOW", 10, minimum=0, maximum=100),
            DB_POOL_RECYCLE_SECONDS=env.integer("NOVA_DB_POOL_RECYCLE_SECONDS", 1800, minimum=60),
            DB_AUTO_CREATE=env.flag("NOVA_DB_AUTO_CREATE", name != "production"),
            JWT_SECRET=env.raw("NOVA_JWT_SECRET", DEV_JWT_SECRET),
            JWT_AUDIENCE=env.text("NOVA_JWT_AUDIENCE", "nova"),
            JWT_LEEWAY_SECONDS=env.integer("NOVA_JWT_LEEWAY_SECONDS", 10, minimum=0, maximum=300),
            CORS_ALLOW_ORIGINS=tuple(
                origin.strip()
                for origin in env.text("NOVA_CORS_ALLOW_ORIGINS").split(",")
                if origin.strip()
            ),
            SPA_DIST_DIR=env.text("NOVA_SPA_DIST_DIR", "apps/nova/dist"),
            SALESOS_CRM_BASE_URL=env.text("SALESOS_CRM_BASE_URL").rstrip("/"),
            SALESOS_CRM_TIMEOUT_SECONDS=env.number("SALESOS_CRM_TIMEOUT_SECONDS", 5.0),
            PROSPECTING_FETCH_ENABLED=env.flag("PROSPECTING_FETCH_ENABLED", False),
            PROSPECTING_PUBLIC_BASE_URL=env.text(
                "PROSPECTING_PUBLIC_BASE_URL", "http://localhost:8000"
            ).rstrip("/"),
            PROSPECTING_DISCOVERY_PROVIDER=env.text(
                "PROSPECTING_DISCOVERY_PROVIDER", "manual"
            ).lower(),
            PROSPECTING_REAL_EMAIL_ENABLED=env.flag("PROSPECTING_REAL_EMAIL_ENABLED", False),
            PROSPECTING_EMAIL_PROVIDER=env.text("PROSPECTING_EMAIL_PROVIDER", "queue").lower(),
            PROSPECTING_EMAIL_API_KEY=env.text("PROSPECTING_EMAIL_API_KEY"),
            PROSPECTING_EMAIL_FROM=env.text("PROSPECTING_EMAIL_FROM").lower(),
            PROSPECTING_SMTP_HOST=env.text("PROSPECTING_SMTP_HOST"),
            PROSPECTING_SMTP_PORT=env.integer("PROSPECTING_SMTP_PORT", 587, minimum=1, maximum=65535),
            PROSPECTING_SMTP_STARTTLS=env.flag("PROSPECTING_SMTP_STARTTLS", True),
            PROSPECTING_SMTP_TIMEOUT_SECONDS=env.number("PROSPECTING_SMTP_TIMEOUT_SECONDS", 20.0),
            PROSPECTING_ANALYSIS_RATE_LIMIT_PER_MINUTE=env.integer(
                "PROSPECTING_ANALYSIS_RATE_LIMIT_PER_MINUTE", 20, minimum=0
            ),
            PROSPECTING_DISCOVERY_RATE_LIMIT_PER_MINUTE=env.integer(
                "PROSPECTING_DISCOVERY_RATE_LIMIT_PER_MINUTE", 10, minimum=0
            ),
            PROSPECTING_DELIVERY_RATE_LIMIT_PER_MINUTE=env.integer(
                "PROSPECTING_DELIVERY_RATE_LIMIT_PER_MINUTE", 30, minimum=0
            ),
            PAGESPEED_API_KEY=env.text("PAGESPEED_API_KEY"),
            PAGESPEED_TIMEOUT_SECONDS=env.number("PAGESPEED_TIMEOUT_SECONDS", 25.0),
            GOOGLE_PLACES_API_KEY=env.text("GOOGLE_PLACES_API_KEY"),
            AGENT_SCHEDULER_ENABLED=env.flag("NOVA_AGENT_SCHEDULER_ENABLED", False),
            SMTP_MAILBOXES=_smtp_mailboxes(env),
        )

    # -- derived views ---------------------------------------------------- #

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    def smtp_mailbox(self, from_address: str | None = None) -> SmtpMailbox | None:
        """The mailbox for ``from_address``, or the default sending mailbox."""
        if not self.SMTP_MAILBOXES:
            return None
        if from_address is None:
            return self.SMTP_MAILBOXES[0]
        wanted = from_address.strip().lower()
        for mailbox in self.SMTP_MAILBOXES:
            if mailbox.from_address == wanted:
                return mailbox
        return None

    def prospecting_smtp_from_addresses(self) -> list[str]:
        return [mailbox.from_address for mailbox in self.SMTP_MAILBOXES]

    def prospecting_email_configured(self) -> bool:
        if self.PROSPECTING_EMAIL_PROVIDER == "resend":
            return bool(self.PROSPECTING_EMAIL_API_KEY and self.PROSPECTING_EMAIL_FROM)
        if self.PROSPECTING_EMAIL_PROVIDER == "smtp_generic":
            return bool(self.SMTP_MAILBOXES)
        return bool(self.PROSPECTING_EMAIL_FROM or self.SMTP_MAILBOXES)

    # -- validation ------------------------------------------------------- #

    def validate(self) -> None:
        """Raise :class:`ConfigError` for any unsafe or incoherent combination."""
        problems: list[str] = []

        if self.ENV not in ENVIRONMENTS:
            problems.append(f"NOVA_ENV must be one of {', '.join(ENVIRONMENTS)}")
        if not self.DATABASE_URL:
            problems.append("NOVA_DATABASE_URL is required")
        if self.PROSPECTING_DISCOVERY_PROVIDER not in DISCOVERY_PROVIDERS:
            problems.append(f"PROSPECTING_DISCOVERY_PROVIDER must be one of {', '.join(DISCOVERY_PROVIDERS)}")
        if self.PROSPECTING_EMAIL_PROVIDER not in EMAIL_PROVIDERS:
            problems.append(f"PROSPECTING_EMAIL_PROVIDER must be one of {', '.join(EMAIL_PROVIDERS)}")
        if self.PROSPECTING_DISCOVERY_PROVIDER == "google_places" and not self.GOOGLE_PLACES_API_KEY:
            problems.append("PROSPECTING_DISCOVERY_PROVIDER=google_places requires GOOGLE_PLACES_API_KEY")
        if self.SALESOS_CRM_BASE_URL and not self.SALESOS_CRM_BASE_URL.startswith(
            ("http://", "https://")
        ):
            problems.append("SALESOS_CRM_BASE_URL must be an absolute http(s) URL")
        if not self.PROSPECTING_PUBLIC_BASE_URL.startswith(("http://", "https://")):
            problems.append("PROSPECTING_PUBLIC_BASE_URL must be an absolute http(s) URL")

        if self.is_production:
            if self.JWT_SECRET == DEV_JWT_SECRET:
                problems.append("NOVA_JWT_SECRET must be set to a private value in production")
            if len(self.JWT_SECRET) < MIN_JWT_SECRET_LENGTH:
                problems.append(f"NOVA_JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")
            if not self.PROSPECTING_PUBLIC_BASE_URL.startswith("https://"):
                problems.append("PROSPECTING_PUBLIC_BASE_URL must be https in production")
            if "*" in self.CORS_ALLOW_ORIGINS:
                problems.append("NOVA_CORS_ALLOW_ORIGINS must not be '*' in production")

        if self.PROSPECTING_REAL_EMAIL_ENABLED:
            # The real-send kill switch may only be on when a real provider is
            # fully configured and public links are served over HTTPS.
            if self.PROSPECTING_EMAIL_PROVIDER not in EXTERNAL_EMAIL_PROVIDERS:
                problems.append(
                    "PROSPECTING_REAL_EMAIL_ENABLED=true requires PROSPECTING_EMAIL_PROVIDER to be "
                    + " or ".join(EXTERNAL_EMAIL_PROVIDERS)
                )
            elif self.PROSPECTING_EMAIL_PROVIDER == "resend":
                if not self.PROSPECTING_EMAIL_API_KEY:
                    problems.append("PROSPECTING_EMAIL_API_KEY is required to send with resend")
                if not self.PROSPECTING_EMAIL_FROM:
                    problems.append("PROSPECTING_EMAIL_FROM is required to send with resend")
            elif not self.SMTP_MAILBOXES:
                problems.append(
                    "PROSPECTING_SMTP_HOST and at least one "
                    "PROSPECTING_SMTP_MAILBOX_<n>_ADDRESS/_PASSWORD pair are required to send "
                    "with smtp_generic"
                )
            if not self.PROSPECTING_PUBLIC_BASE_URL.startswith("https://"):
                problems.append("PROSPECTING_REAL_EMAIL_ENABLED=true requires an https PROSPECTING_PUBLIC_BASE_URL")

        if problems:
            raise ConfigError("Invalid Nova configuration: " + "; ".join(problems))

    def warnings(self) -> list[str]:
        """Non-fatal advisories: safe to run, but an operator should know.

        These are deliberately not errors - refusing to boot would break a
        deliberately small single-node pilot - but they are logged at startup
        and surfaced on /health/ready so they cannot pass unnoticed.
        """
        advisories: list[str] = []
        if self.is_production:
            if self.DATABASE_URL.startswith("sqlite"):
                advisories.append(
                    "NOVA_DATABASE_URL uses SQLite: single-writer only, no concurrent workers"
                )
            if self.DB_AUTO_CREATE:
                advisories.append(
                    "NOVA_DB_AUTO_CREATE is on in production: schema should come from "
                    "'alembic upgrade head' instead"
                )
            if not self.CORS_ALLOW_ORIGINS:
                advisories.append(
                    "NOVA_CORS_ALLOW_ORIGINS is empty: only same-origin browser clients can call the API"
                )
        if self.PROSPECTING_FETCH_ENABLED and not self.PAGESPEED_API_KEY:
            advisories.append("PAGESPEED_API_KEY is unset: analyses run without Lighthouse enrichment")
        if not self.SALESOS_CRM_BASE_URL:
            advisories.append("SALESOS_CRM_BASE_URL is unset: CRM promotion will fail closed")
        return advisories

    def safe_summary(self) -> dict[str, object]:
        """Non-sensitive configuration view for logs and health output."""
        return {
            "env": self.ENV,
            "database": self.DATABASE_URL.split("://", 1)[0] or "unknown",
            "fetch_enabled": self.PROSPECTING_FETCH_ENABLED,
            "discovery_provider": self.PROSPECTING_DISCOVERY_PROVIDER,
            "email_provider": self.PROSPECTING_EMAIL_PROVIDER,
            "real_email_enabled": self.PROSPECTING_REAL_EMAIL_ENABLED,
            "pagespeed_configured": bool(self.PAGESPEED_API_KEY),
            "crm_configured": bool(self.SALESOS_CRM_BASE_URL),
            "smtp_mailboxes": len(self.SMTP_MAILBOXES),
            "scheduler_enabled": self.AGENT_SCHEDULER_ENABLED,
        }


settings = Settings.from_env()
