#!/usr/bin/env python3
"""Fail if the migrated schema and the ORM models have drifted apart.

A migration chain that no longer produces the schema the code expects is a
production outage waiting for the next deploy, and it is invisible in a test
suite that creates its tables straight from the models. This compares the two
schemas object by object.

Usage:  NOVA_DATABASE_URL=sqlite:///./ci.db python scripts/check-migration-parity.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.db.session import Base  # noqa: E402
from app.prospecting import models  # noqa: E402,F401 -- registers Nova-owned tables
from app.tenancy import service  # noqa: E402,F401 -- registers the audit table

IGNORED_TABLES = {"alembic_version"}


def describe(url: str) -> dict[str, dict[str, object]]:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        schema: dict[str, dict[str, object]] = {}
        for table in sorted(inspector.get_table_names()):
            if table in IGNORED_TABLES:
                continue
            schema[table] = {
                "columns": {
                    column["name"]: {
                        "type": str(column["type"]),
                        "nullable": bool(column["nullable"]),
                    }
                    for column in inspector.get_columns(table)
                },
                "indexes": sorted(
                    (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                    for index in inspector.get_indexes(table)
                ),
                "primary_key": tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
                "unique": sorted(
                    (constraint["name"], tuple(constraint["column_names"]))
                    for constraint in inspector.get_unique_constraints(table)
                ),
            }
        return schema
    finally:
        engine.dispose()


def main() -> int:
    migrated_url = os.environ.get("NOVA_DATABASE_URL")
    if not migrated_url:
        print("NOVA_DATABASE_URL must point at a database already migrated to head", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as workdir:
        model_url = f"sqlite:///{Path(workdir) / 'models.db'}"
        model_engine = create_engine(model_url)
        Base.metadata.create_all(model_engine)
        model_engine.dispose()

        migrated = describe(migrated_url)
        expected = describe(model_url)

    problems: list[str] = []
    for table in sorted(set(expected) - set(migrated)):
        problems.append(f"table missing from the migrations: {table}")
    for table in sorted(set(migrated) - set(expected)):
        problems.append(f"table created by migrations but absent from the models: {table}")
    for table in sorted(set(expected) & set(migrated)):
        for key in ("columns", "indexes", "primary_key", "unique"):
            if expected[table][key] != migrated[table][key]:
                problems.append(
                    f"{table}.{key} differs\n  models:     {expected[table][key]}\n"
                    f"  migrations: {migrated[table][key]}"
                )

    if problems:
        print("Migration parity check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"Migration parity OK: {len(expected)} tables match the models exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
