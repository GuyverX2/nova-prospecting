"""Documentation that is checkable is checked, so it cannot silently rot."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = (REPO_ROOT / "services/api/app/core/config.py").read_text(encoding="utf-8")
ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

#: Read with a computed name (PROSPECTING_SMTP_MAILBOX_<n>_*), documented by example.
DYNAMIC_SUFFIXES = {"ADDRESS", "PASSWORD"}
#: Consumed by the Vite build, not by the Python service.
FRONTEND_ONLY = {"VITE_NOVA_API_URL"}


def _variables_read_by_config() -> set[str]:
    names = set(re.findall(r'env\.(?:raw|text|flag|integer|number)\(\s*"([A-Z0-9_]+)"', CONFIG_SOURCE))
    names |= set(re.findall(r'f"\{prefix\}([A-Z]+)"', CONFIG_SOURCE))
    return names - DYNAMIC_SUFFIXES


def _variables_documented() -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE, re.MULTILINE))


def test_every_setting_is_documented_in_env_example():
    undocumented = _variables_read_by_config() - _variables_documented()
    assert not undocumented, f"missing from .env.example: {sorted(undocumented)}"


def test_env_example_documents_nothing_imaginary():
    documented = _variables_documented() - FRONTEND_ONLY
    mailbox_pattern = re.compile(r"^PROSPECTING_SMTP_MAILBOX_\d+_(ADDRESS|PASSWORD)$")
    unread = {
        name
        for name in documented - _variables_read_by_config()
        if not mailbox_pattern.match(name)
    }
    assert not unread, f".env.example documents variables nothing reads: {sorted(unread)}"


def test_env_example_contains_no_real_secret():
    for line in ENV_EXAMPLE.splitlines():
        if line.startswith("PROSPECTING_SMTP_MAILBOX_") and "PASSWORD" in line:
            assert line.endswith("="), "example passwords must be empty"
        if line.startswith("PROSPECTING_EMAIL_API_KEY"):
            assert line.strip() == "PROSPECTING_EMAIL_API_KEY="


def test_readme_documents_how_to_run_and_migrate():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for expected in ("alembic upgrade head", "/health/ready", "pytest"):
        assert expected in readme, f"README must document {expected}"
    # A reproducible frontend install means `npm ci` (lockfile), never `npm install`.
    assert re.search(r"npm\b[^\n]*\bci\b", readme), "README must document a lockfile install"


def test_makefile_targets_referenced_by_deploy_scripts_exist():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-zA-Z0-9_-]+):", makefile, re.MULTILINE))
    referenced: set[str] = set()
    for script in (REPO_ROOT / "scripts" / "deploy").iterdir():
        for match in re.findall(r"make ([a-z0-9-]+)", script.read_text(encoding="utf-8")):
            referenced.add(match)
    assert referenced <= targets, f"deploy scripts reference missing targets: {sorted(referenced - targets)}"
