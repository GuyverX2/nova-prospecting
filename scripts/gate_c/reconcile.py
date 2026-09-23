#!/usr/bin/env python3
"""Fail-closed reconciliation for a Gate C export/import manifest.

This tool deliberately receives only metadata (counts, stable ids and tenant
ownership), never database credentials or row payloads.  The operator creates
the manifests next to the controlled export/import jobs; this verifies that the
target is an exact, tenant-preserving copy before any write-authority switch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


TABLES = (
    "prospecting_campaigns",
    "website_prospects",
    "website_analyses",
    "website_proposals",
    "prospecting_policies",
    "prospect_suppressions",
)


class ReconciliationError(ValueError):
    pass


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read manifest {path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ReconciliationError("manifest schema_version must be 1")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise ReconciliationError("manifest must contain exactly the six Nova-owned tables")
    return payload


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def reconcile(source: dict[str, Any], target: dict[str, Any]) -> dict[str, int]:
    """Require exact table counts, id digests, and tenant-ownership digests."""
    result: dict[str, int] = {}
    for table in TABLES:
        source_table = source["tables"][table]
        target_table = target["tables"][table]
        for key in ("count", "id_sha256", "tenant_ownership_sha256"):
            if source_table.get(key) != target_table.get(key):
                raise ReconciliationError(f"{table}: {key} differs")
        count = source_table.get("count")
        if not isinstance(count, int) or count < 0:
            raise ReconciliationError(f"{table}: count must be a non-negative integer")
        result[table] = count
    return result


def manifest_for_records(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Create a deterministic test/offline manifest from redacted record metadata."""
    if set(records) != set(TABLES):
        raise ReconciliationError("records must contain exactly the six Nova-owned tables")
    tables: dict[str, dict[str, Any]] = {}
    for table, rows in records.items():
        ids = sorted(str(row["id"]) for row in rows)
        ownership = sorted((str(row["id"]), str(row["tenant_id"])) for row in rows)
        tables[table] = {
            "count": len(rows),
            "id_sha256": hashlib.sha256(_canonical(ids).encode()).hexdigest(),
            "tenant_ownership_sha256": hashlib.sha256(_canonical(ownership).encode()).hexdigest(),
        }
    return {"schema_version": 1, "tables": tables}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Gate C export/import manifests")
    parser.add_argument("source", type=Path, help="source metadata manifest")
    parser.add_argument("target", type=Path, help="target metadata manifest")
    args = parser.parse_args()
    counts = reconcile(_read_manifest(args.source), _read_manifest(args.target))
    print(json.dumps({"result": "ok", "tables": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
