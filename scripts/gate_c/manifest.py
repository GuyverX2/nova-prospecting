"""Create a metadata-only Gate C manifest from one database connection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from .reconcile import TABLES, ReconciliationError, manifest_for_records


class ManifestError(ValueError):
    pass


def _sqlite_path(database_url: str) -> Path | None:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite" or parsed.path in ("", "/:memory:"):
        return None
    return Path(parsed.path)


def manifest_from_database(database_url: str) -> dict[str, Any]:
    """Read only stable ID + tenant metadata from the six Nova tables.

    Operators must pass a read-only credential for remote databases. SQLite is
    checked before connection so a typo cannot silently create a new source DB.
    """
    sqlite_path = _sqlite_path(database_url)
    if sqlite_path is not None and not sqlite_path.exists():
        raise ManifestError("SQLite source database does not exist")
    engine = create_engine(database_url)
    try:
        names = set(inspect(engine).get_table_names())
        missing = set(TABLES) - names
        if missing:
            raise ManifestError(f"source is missing Nova-owned tables: {', '.join(sorted(missing))}")
        metadata = MetaData()
        records: dict[str, list[dict[str, Any]]] = {}
        with engine.connect() as connection:
            for name in TABLES:
                table = Table(name, metadata, autoload_with=connection)
                if "id" not in table.c or "tenant_id" not in table.c:
                    raise ManifestError(f"{name}: id and tenant_id columns are required")
                records[name] = [
                    {"id": row.id, "tenant_id": row.tenant_id}
                    for row in connection.execute(select(table.c.id, table.c.tenant_id))
                ]
    except SQLAlchemyError as exc:
        raise ManifestError("cannot read source database") from exc
    finally:
        engine.dispose()
    try:
        return manifest_for_records(records)
    except ReconciliationError as exc:
        raise ManifestError(str(exc)) from exc


def write_manifest(database_url: str, output: Path) -> None:
    """Write only count/hash metadata; output must be a new file."""
    if output.exists():
        raise ManifestError("refusing to overwrite an existing manifest")
    manifest = manifest_from_database(database_url)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
