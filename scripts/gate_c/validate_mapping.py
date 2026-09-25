#!/usr/bin/env python3
"""Validate an operator-supplied Gate C identifier map without connecting to a DB."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mapping import MappingError, _validated_mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Gate C tenant/user identifier mapping")
    parser.add_argument("mapping", type=Path, help="local JSON file with tenant_ids and user_subjects maps")
    args = parser.parse_args()
    try:
        document = json.loads(args.mapping.read_text(encoding="utf-8"))
        tenants = _validated_mapping(document.get("tenant_ids", {}), name="tenant_ids")
        subjects = _validated_mapping(document.get("user_subjects", {}), name="user_subjects")
        reattributions = document.get("subject_reattributions", {})
        if not isinstance(reattributions, dict):
            raise MappingError("subject_reattributions must be an object")
        for src, owner in reattributions.items():
            if str(src) in subjects:
                raise MappingError(
                    f"subject_reattribution source {src!r} must not also be in user_subjects"
                )
            if str(owner) not in subjects:
                raise MappingError(
                    f"subject_reattribution target {owner!r} must be present in user_subjects"
                )
    except (OSError, json.JSONDecodeError, MappingError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "result": "ok",
                "tenant_mappings": len(tenants),
                "subject_mappings": len(subjects),
                "subject_reattributions": len(reattributions),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
