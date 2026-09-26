#!/usr/bin/env python3
"""Configure H8c Nova smtp_generic for Google Workspace (Gmail SMTP).

triplusmedia.com MX → Google (aspmx.l.google.com), not Loopia.
Credentials go only into a gitignored env file — never printed or committed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# The service reads one environment file at the repository root (or whatever the
# host passes with --env-file); services/api/.env was never read by anything.
DEFAULT_ENV = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# H8c dual-valid From allowlist + Gmail SMTP relay for Google Workspace mailboxes.
NOVA_GMAIL_KEYS: tuple[tuple[str, str], ...] = (
    ("PROSPECTING_FETCH_ENABLED", "true"),
    ("PROSPECTING_DISCOVERY_PROVIDER", "disabled"),
    ("PROSPECTING_EMAIL_PROVIDER", "smtp_generic"),
    ("PROSPECTING_REAL_EMAIL_ENABLED", "true"),
    ("PROSPECTING_PUBLIC_BASE_URL", "https://salesos.se"),
    ("PROSPECTING_SMTP_HOST", "smtp.gmail.com"),
    ("PROSPECTING_SMTP_PORT", "587"),
    ("PROSPECTING_SMTP_STARTTLS", "true"),
    ("PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "martin@triplusmedia.com"),
    ("PROSPECTING_SMTP_MAILBOX_2_ADDRESS", "micha@triplusmedia.com"),
)

#: Documented default deployment (dual_valid NOVA-SMTP-GENERIC-HOST-20260817).
#: Override with --mailbox for any other host.
DEFAULT_MAILBOXES: tuple[tuple[str, str], ...] = (
    ("martin@triplusmedia.com", "PROSPECTING_SMTP_MAILBOX_1_PASSWORD"),
    ("micha@triplusmedia.com", "PROSPECTING_SMTP_MAILBOX_2_PASSWORD"),
)


def resolve_mailboxes(addresses: list[str] | None) -> tuple[tuple[str, str], ...]:
    """Pair each sending address with the env var that holds its password."""
    if not addresses:
        return DEFAULT_MAILBOXES
    return tuple(
        (address.strip().lower(), f"PROSPECTING_SMTP_MAILBOX_{index}_PASSWORD")
        for index, address in enumerate(addresses, start=1)
    )


def upsert_env_keys(path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            lines[index] = f"{key}={updates[key]}"
            seen.add(key)
    missing = [key for key in updates if key not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Nova H8c — Google Workspace via smtp.gmail.com (configure-nova-smtp.py)")
        for key in missing:
            lines.append(f"{key}={updates[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def normalize_google_secret(raw: str) -> str:
    """Strip whitespace; Google App Passwords are often pasted as 'xxxx xxxx xxxx xxxx'."""
    return re.sub(r"\s+", "", raw.strip())


def prompt_google_secret(address: str, *, env_var: str) -> str:
    from_env = os.environ.get(env_var, "").strip()
    if from_env:
        return normalize_google_secret(from_env)
    print(f"\nMailbox: {address}")
    print("  Prefer a Google App Password (16 chars) if 2FA is on.")
    print("  Spaces in pasted App Passwords are removed automatically.")
    while True:
        first = normalize_google_secret(getpass.getpass(f"  Google password / App Password for {address}: "))
        if not first:
            print("  Password cannot be empty.", file=sys.stderr)
            continue
        confirm = normalize_google_secret(getpass.getpass("  Confirm: "))
        if first != confirm:
            print("  Entries did not match — try again.", file=sys.stderr)
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure Nova H8c SMTP for Google Workspace (smtp.gmail.com)."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV,
        help=f"Target env file (default: {DEFAULT_ENV.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--mailbox",
        action="append",
        metavar="ADDRESS",
        help=(
            "Sending mailbox to configure; repeat for more. "
            f"Default: {', '.join(address for address, _ in DEFAULT_MAILBOXES)}"
        ),
    )
    parser.add_argument(
        "--init-from-example",
        action="store_true",
        help="Copy .env.example when the target file is missing",
    )
    args = parser.parse_args()
    env_file: Path = args.env_file
    if not env_file.is_absolute():
        env_file = (REPO_ROOT / env_file).resolve()

    print("Nova SMTP configure — Google Workspace")
    print("  Host:     smtp.gmail.com:587 STARTTLS")
    print(f"  From:     {', '.join(address for address, _ in resolve_mailboxes(args.mailbox))}")
    print("  Note:     triplusmedia.com is Google mail (not Loopia/mailcluster)")
    print(f"  Env file: {env_file}")

    if not env_file.is_file():
        if args.init_from_example or env_file == DEFAULT_ENV:
            if not ENV_EXAMPLE.is_file():
                raise SystemExit(f"Missing template: {ENV_EXAMPLE}")
            env_file.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
            print(f"Created {env_file} from .env.example")
        else:
            raise SystemExit(f"Environment file not found: {env_file}")

    mailboxes = resolve_mailboxes(args.mailbox)
    updates = {key: value for key, value in NOVA_GMAIL_KEYS if not key.startswith("PROSPECTING_SMTP_MAILBOX_")}
    for index, (address, env_var) in enumerate(mailboxes, start=1):
        updates[f"PROSPECTING_SMTP_MAILBOX_{index}_ADDRESS"] = address
        updates[env_var] = prompt_google_secret(address, env_var=env_var)

    upsert_env_keys(env_file, updates)
    print()
    print(f"Updated Gmail SMTP keys in {env_file} (passwords not shown).")
    print("PROSPECTING_SMTP_HOST=smtp.gmail.com")
    print("Next:")
    print("  make smoke-nova-smtp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
