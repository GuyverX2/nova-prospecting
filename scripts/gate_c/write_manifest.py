#!/usr/bin/env python3
"""Write a Gate C metadata manifest from a read-only database connection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .manifest import ManifestError, write_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a metadata-only Gate C manifest")
    parser.add_argument("--database-url", required=True, help="read-only source or target database URL")
    parser.add_argument("--output", required=True, help="new manifest path; existing files are never overwritten")
    parser.add_argument(
        "--mapping",
        type=Path,
        help="optional legacy-identifier mapping file; converts tenant ownership in memory",
    )
    args = parser.parse_args()
    tenant_ids: dict[str, str] | None = None
    if args.mapping is not None:
        try:
            payload: dict[str, Any] = json.loads(args.mapping.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"cannot read mapping file: {exc}")
        if not isinstance(payload, dict) or not isinstance(payload.get("tenant_ids"), dict):
            parser.error("mapping file must contain a tenant_ids object")
        tenant_ids = dict(payload["tenant_ids"])
    try:
        write_manifest(args.database_url, args.output, tenant_ids=tenant_ids)
    except ManifestError as exc:
        parser.error(str(exc))
    print("result=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
