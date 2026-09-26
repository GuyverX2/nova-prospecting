#!/usr/bin/env python3
"""Controlled SalesOS -> standalone Nova row copy for a Gate C rehearsal.

Contract:
  * the source URL must be a **read-only** credential; this tool only runs
    ``SELECT`` statements against it and never writes there.
  * the target must already contain exactly the empty Nova-owned schema
    (alembic head) plus ``alembic_version``; anything else aborts the run.
  * every ownership reference is converted in memory with the reviewed
    legacy-identifier mapping; row payloads and credentials are never written
    to Git or disk.
  * evidence is metadata-only: the operator reconciles the deterministic
    target manifest against the pre-existing source manifest.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, table
from sqlalchemy.engine import Connection

from .manifest import manifest_from_database
from .mapping import _SUBJECT_FIELDS, map_legacy_row
from .reconcile import AUDIT_TABLE, NOVA_OWNED_TABLES, TABLES


class ExportImportError(ValueError):
    pass


CHUNK_SIZE = 1000


def _load_mapping(path: Path) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportImportError(f"cannot read mapping file {path}: {exc}") from exc
    required = {"tenant_ids", "user_subjects"}
    allowed = required | {"subject_reattributions"}
    if not required <= set(payload):
        raise ExportImportError("mapping file must contain tenant_ids and user_subjects")
    if set(payload) > allowed:
        raise ExportImportError(
            "mapping file may only contain tenant_ids, user_subjects"
            " and subject_reattributions"
        )
    tenant_ids = payload["tenant_ids"]
    user_subjects = payload["user_subjects"]
    if not isinstance(tenant_ids, dict) or not isinstance(user_subjects, dict):
        raise ExportImportError("mapping file sections must be objects")
    if not tenant_ids:
        raise ExportImportError("tenant_ids must be reviewed and non-empty")
    reattributions = payload.get("subject_reattributions", {})
    if not isinstance(reattributions, dict):
        raise ExportImportError("subject_reattributions must be an object")
    for src, owner in reattributions.items():
        if str(src) in user_subjects:
            raise ExportImportError(
                f"subject_reattribution source {src!r} must not also be in user_subjects"
            )
        if str(owner) not in user_subjects:
            raise ExportImportError(
                f"subject_reattribution target {owner!r} must be present in user_subjects"
            )
    reattributions = {str(k): str(v) for k, v in reattributions.items()}
    return {
        "tenant_ids": tenant_ids,
        "user_subjects": user_subjects,
        "subject_reattributions": reattributions,
    }


def _converted_batches(
    connection: Connection,
    source_table: Table,
    name: str,
    mapping: dict[str, dict[str, str]],
) -> Iterator[list[dict[str, Any]]]:
    """Stream one source table, converting ownership references in memory."""
    user_fields = [source_field for (source_field, _, _) in _SUBJECT_FIELDS[name]]
    reattributions = mapping["subject_reattributions"]
    buffer: list[dict[str, Any]] = []
    for row in connection.execute(select(source_table)).mappings():
        record = dict(row)
        for source_field in user_fields:
            value = record.get(source_field)
            if value is not None and str(value) in reattributions:
                record[source_field] = reattributions[str(value)]
        buffer.append(
            map_legacy_row(
                name,
                record,
                tenant_ids=mapping["tenant_ids"],
                user_subjects=mapping["user_subjects"],
            )
        )
        if len(buffer) >= CHUNK_SIZE:
            yield buffer
            buffer = []
    if buffer:
        yield buffer


def export_import(
    *,
    source_url: str,
    target_url: str,
    mapping: Path,
    output_manifest: Path,
) -> dict[str, int]:
    if source_url == target_url:
        raise ExportImportError("source and target URLs must be different credentials")
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)
    counts: dict[str, int] = {}
    try:
        source_tables = set(inspect(source_engine).get_table_names())
        missing = set(TABLES) - source_tables
        if missing:
            raise ExportImportError(
                f"source database is missing Nova-owned tables: {', '.join(sorted(missing))}"
            )
        target_tables = set(inspect(target_engine).get_table_names())
        target_extras = target_tables - set(NOVA_OWNED_TABLES) - {"alembic_version"}
        if target_extras:
            raise ExportImportError(
                "target schema is not exactly the Nova-owned tables: "
                + ", ".join(sorted(target_extras))
            )
        target_missing = set(TABLES) - target_tables
        if target_missing:
            raise ExportImportError(
                "target database is missing Nova-owned tables: " + ", ".join(sorted(target_missing))
            )
        if AUDIT_TABLE in target_tables:
            # A target that already holds audit rows is not a fresh import
            # target; refuse rather than interleaving two environments' trails.
            with target_engine.connect() as probe:
                audit_rows = probe.execute(
                    select(func.count()).select_from(table(AUDIT_TABLE))
                ).scalar_one()
            if audit_rows:
                raise ExportImportError("target audit_events must be empty before an import")

        _mapping = _load_mapping(Path(mapping))
        with (
            source_engine.connect().execution_options(stream_results=True) as source_connection,
            target_engine.begin() as target_connection,
        ):
            for name in TABLES:
                source_table = Table(name, MetaData(), autoload_with=source_connection)
                target_table = Table(name, MetaData(), autoload_with=target_connection)
                inserted = 0
                for batch in _converted_batches(source_connection, source_table, name, _mapping):
                    target_connection.execute(target_table.insert(), batch)
                    inserted += len(batch)
                counts[name] = inserted

        manifest = manifest_from_database(target_url)
        _write_output_manifest(output_manifest, manifest)
    finally:
        source_engine.dispose()
        target_engine.dispose()
    return counts


def _write_output_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if path.exists():
        raise ExportImportError("refusing to overwrite an existing manifest")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rehearse a controlled SalesOS -> Nova row copy")
    parser.add_argument("--source-url", required=True, help="read-only source credential (never printed)")
    parser.add_argument("--target-url", required=True, help="empty Nova-owned schema credential (never printed)")
    parser.add_argument("--mapping", type=Path, required=True, help="legacy identifier mapping file")
    parser.add_argument("--output-manifest", type=Path, required=True, help="new metadata-only target manifest")
    args = parser.parse_args()
    counts = export_import(
        source_url=args.source_url,
        target_url=args.target_url,
        mapping=args.mapping,
        output_manifest=args.output_manifest,
    )
    print(json.dumps({"result": "ok", "tables": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
