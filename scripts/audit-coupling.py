#!/usr/bin/env python3
"""Fail when standalone Nova source reaches into a SalesOS implementation."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "services/api/app", ROOT / "apps/nova/src"]
FORBIDDEN = (
    "/repos/salesos",
    "from app.models.sales_desk",
    "from app.sales_desk",
    "from app.schemas.sales_desk",
    'ForeignKey("users.id")',
    'ForeignKey("tenants.id")',
)


def main() -> int:
    violations: list[str] = []
    for source in SOURCES:
        for path in source.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN:
                if forbidden in text:
                    violations.append(f"{path.relative_to(ROOT)}: {forbidden}")
    if violations:
        raise SystemExit("Nova coupling audit failed:\n" + "\n".join(violations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
