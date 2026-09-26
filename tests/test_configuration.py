"""Startup configuration must fail closed, never boot into an unsafe state."""
from __future__ import annotations

import pytest

from app.core.config import ConfigError, Settings

BASE_ENV = {
    "NOVA_ENV": "production",
    "NOVA_JWT_SECRET": "a-production-secret-that-is-long-enough-1",
    "NOVA_DATABASE_URL": "postgresql+psycopg://nova:pw@db/nova",
    "NOVA_CORS_ALLOW_ORIGINS": "https://nova.example",
    "PROSPECTING_PUBLIC_BASE_URL": "https://nova.example",
}


def _settings(**overrides) -> Settings:
    env = {**BASE_ENV, **overrides}
    return Settings.from_env({key: value for key, value in env.items() if value is not None})


def test_a_valid_production_configuration_passes():
    _settings().validate()


def test_the_development_default_secret_is_refused_in_production():
    with pytest.raises(ConfigError) as exc:
        _settings(NOVA_JWT_SECRET=None).validate()
    assert "NOVA_JWT_SECRET" in str(exc.value)


def test_short_secrets_are_refused():
    with pytest.raises(ConfigError):
        _settings(NOVA_JWT_SECRET="too-short").validate()


def test_sqlite_in_production_is_a_loud_warning_not_a_silent_default():
    """A single-node pilot may run SQLite, but never by accident."""
    settings = _settings(NOVA_DATABASE_URL="sqlite:///./nova.db")
    settings.validate()
    assert any("SQLite" in warning for warning in settings.warnings())
    assert not any("SQLite" in warning for warning in _settings().warnings())


def test_auto_create_in_production_is_flagged():
    assert any("NOVA_DB_AUTO_CREATE" in warning for warning in _settings(NOVA_DB_AUTO_CREATE="true").warnings())
    assert not any("NOVA_DB_AUTO_CREATE" in warning for warning in _settings().warnings())


def test_wildcard_cors_is_refused_in_production():
    with pytest.raises(ConfigError):
        _settings(NOVA_CORS_ALLOW_ORIGINS="*").validate()


def test_real_email_requires_a_provider_and_sender():
    with pytest.raises(ConfigError) as exc:
        _settings(
            PROSPECTING_REAL_EMAIL_ENABLED="true", PROSPECTING_EMAIL_PROVIDER="resend"
        ).validate()
    message = str(exc.value)
    assert "PROSPECTING_EMAIL_API_KEY" in message
    assert "PROSPECTING_EMAIL_FROM" in message


def test_real_email_over_smtp_requires_a_mailbox():
    with pytest.raises(ConfigError) as exc:
        _settings(
            PROSPECTING_REAL_EMAIL_ENABLED="true",
            PROSPECTING_EMAIL_PROVIDER="smtp_generic",
        ).validate()
    assert "PROSPECTING_SMTP_MAILBOX" in str(exc.value)


def test_fully_configured_real_email_passes():
    _settings(
        PROSPECTING_REAL_EMAIL_ENABLED="true",
        PROSPECTING_EMAIL_PROVIDER="resend",
        PROSPECTING_EMAIL_API_KEY="re_live_key",
        PROSPECTING_EMAIL_FROM="prospekt@nova.example",
    ).validate()


def test_unknown_provider_names_are_refused():
    with pytest.raises(ConfigError):
        _settings(PROSPECTING_EMAIL_PROVIDER="smoke-signals").validate()
    with pytest.raises(ConfigError):
        _settings(PROSPECTING_DISCOVERY_PROVIDER="yellow-pages").validate()


def test_google_places_discovery_requires_a_key():
    with pytest.raises(ConfigError) as exc:
        _settings(PROSPECTING_DISCOVERY_PROVIDER="google_places").validate()
    assert "GOOGLE_PLACES_API_KEY" in str(exc.value)


def test_public_base_url_must_be_absolute_https_in_production():
    with pytest.raises(ConfigError):
        _settings(PROSPECTING_PUBLIC_BASE_URL="localhost:8000").validate()


def test_crm_base_url_must_be_absolute():
    with pytest.raises(ConfigError):
        _settings(SALESOS_CRM_BASE_URL="salesos.se").validate()


def test_numeric_settings_reject_unparsable_values():
    with pytest.raises(ConfigError):
        _settings(NOVA_DB_POOL_SIZE="plenty")
    with pytest.raises(ConfigError):
        _settings(PROSPECTING_SMTP_PORT="not-a-port")


def test_all_smtp_mailboxes_are_read_and_validated():
    settings = _settings(
        PROSPECTING_EMAIL_PROVIDER="smtp_generic",
        PROSPECTING_SMTP_HOST="smtp.example",
        PROSPECTING_SMTP_MAILBOX_1_ADDRESS="one@example",
        PROSPECTING_SMTP_MAILBOX_1_PASSWORD="pw1",
        PROSPECTING_SMTP_MAILBOX_2_ADDRESS="two@example",
        PROSPECTING_SMTP_MAILBOX_2_PASSWORD="pw2",
    )
    assert [mailbox.from_address for mailbox in settings.SMTP_MAILBOXES] == [
        "one@example",
        "two@example",
    ]
    settings.validate()


def test_an_incomplete_extra_mailbox_is_refused():
    with pytest.raises(ConfigError) as exc:
        _settings(
            PROSPECTING_EMAIL_PROVIDER="smtp_generic",
            PROSPECTING_SMTP_HOST="smtp.example",
            PROSPECTING_SMTP_MAILBOX_1_ADDRESS="one@example",
            PROSPECTING_SMTP_MAILBOX_1_PASSWORD="pw1",
            PROSPECTING_SMTP_MAILBOX_2_ADDRESS="two@example",
        ).validate()
    assert "PROSPECTING_SMTP_MAILBOX_2" in str(exc.value)


def test_the_safe_summary_never_contains_a_secret():
    settings = _settings(
        PROSPECTING_EMAIL_API_KEY="re_live_supersecret",
        GOOGLE_PLACES_API_KEY="places-secret",
        PROSPECTING_SMTP_HOST="smtp.example",
        PROSPECTING_SMTP_MAILBOX_1_ADDRESS="one@example",
        PROSPECTING_SMTP_MAILBOX_1_PASSWORD="smtp-secret",
    )
    rendered = repr(settings.safe_summary()) + repr(settings.warnings()) + repr(settings)
    for secret in (
        "re_live_supersecret",
        "places-secret",
        "smtp-secret",
        settings.JWT_SECRET,
    ):
        assert secret not in rendered


def test_development_defaults_are_usable_without_any_environment():
    settings = Settings.from_env({})
    settings.validate()
    assert settings.ENV == "development"
    assert settings.DB_AUTO_CREATE is True
    assert settings.PROSPECTING_REAL_EMAIL_ENABLED is False
