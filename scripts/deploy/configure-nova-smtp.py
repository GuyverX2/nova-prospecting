#!/usr/bin/env python3
"""Configure H8c Nova smtp_generic env keys without printing passwords."""
from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = REPO_ROOT / "services" / "api" / ".env"
ENV_EXAMPLE = REPO_ROOT / "services" / "api" / ".env.example"

NOVA_SMTP_KEYS: tuple[tuple[str, str], ...] = (
    ("PROSPECTING_FETCH_ENABLED", "true"),
    ("PROSPECTING_DISCOVERY_PROVIDER", "disabled"),
    ("PROSPECTING_EMAIL_PROVIDER", "smtp_generic"),
    ("PROSPECTING_REAL_EMAIL_ENABLED", "true"),
    ("PROSPECTING_PUBLIC_BASE_URL", "https://salesos.se"),
    ("PROSPECTING_SMTP_HOST", "mailcluster.loopia.se"),
    ("PROSPECTING_SMTP_PORT", "587"),
    ("PROSPECTING_SMTP_STARTTLS", "true"),
    ("PROSPECTING_SMTP_MAILBOX_1_ADDRESS", "martin@triplusmedia.com"),
    ("PROSPECTING_SMTP_MAILBOX_2_ADDRESS", "micha@triplusmedia.com"),
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
        lines.append("# Nova website prospecting — H8c smtp_generic (configure-nova-smtp.py)")
        for key in missing:
            lines.append(f"{key}={updates[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def prompt_password(label: str, *, env_var: str) -> str:
    from_env = os.environ.get(env_var, "").strip()
    if from_env:
        return from_env
    while True:
        first = getpass.getpass(f"{label} password: ")
        if first.strip():
            return first
        print("Password cannot be empty.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Nova H8c smtp_generic env (secrets stay local).")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV,
        help=f"Target env file (default: {DEFAULT_ENV.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--init-from-example",
        action="store_true",
        help="Copy services/api/.env.example when the target file is missing",
    )
    args = parser.parse_args()
    env_file: Path = args.env_file

    if not env_file.is_file():
        if args.init_from_example or env_file == DEFAULT_ENV:
            if not ENV_EXAMPLE.is_file():
                raise SystemExit(f"Missing template: {ENV_EXAMPLE}")
            env_file.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
            print(f"Created {env_file} from .env.example")
        else:
            raise SystemExit(f"Environment file not found: {env_file}")

    updates = dict(NOVA_SMTP_KEYS)
    updates["PROSPECTING_SMTP_MAILBOX_1_PASSWORD"] = prompt_password(
        "martin@triplusmedia.com",
        env_var="PROSPECTING_SMTP_MAILBOX_1_PASSWORD",
    )
    updates["PROSPECTING_SMTP_MAILBOX_2_PASSWORD"] = prompt_password(
        "micha@triplusmedia.com",
        env_var="PROSPECTING_SMTP_MAILBOX_2_PASSWORD",
    )
    upsert_env_keys(env_file, updates)
    print(f"Updated Nova SMTP keys in {env_file} (passwords not shown).")
    print("Next:")
    print("  make smoke-nova-smtp          # verify SMTP login")
    print("  make run-demo-api             # or restart production API")
    print("  https://salesos.se/nova       # live workspace (production)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
