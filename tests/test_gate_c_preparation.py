from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from app.db.session import Base
from app.prospecting import models  # noqa: F401 -- registers the six target tables
from scripts.gate_c.manifest import ManifestError, manifest_from_database, write_manifest
from scripts.gate_c.mapping import MappingError, map_legacy_row
from scripts.gate_c.reconcile import (
    NOVA_OWNED_TABLES,
    TABLES,
    ReconciliationError,
    manifest_for_records,
    reconcile,
)


def _records(tenant: str = "tenant-1"):
    return {
        table: [{"id": f"{index}-1", "tenant_id": tenant}]
        for index, table in enumerate(TABLES, start=1)
    }


def test_manifest_reconciliation_requires_ids_and_tenant_ownership_to_match():
    source = manifest_for_records(_records())
    assert reconcile(source, manifest_for_records(_records())) == dict.fromkeys(TABLES, 1)

    changed_owner = _records("tenant-2")
    with pytest.raises(ReconciliationError, match="tenant_ownership_sha256 differs"):
        reconcile(source, manifest_for_records(changed_owner))


def test_legacy_identifier_mapping_requires_explicit_tenant_and_subjects():
    converted = map_legacy_row(
        "website_proposals",
        {"id": "wp_1", "tenant_id": 7, "created_by_user_id": 12, "approved_by_user_id": None},
        tenant_ids={"7": "tenant-formkok"},
        user_subjects={"12": "user-operator"},
    )
    assert converted == {
        "id": "wp_1",
        "tenant_id": "tenant-formkok",
        "created_by_subject": "user-operator",
        "approved_by_subject": None,
    }
    with pytest.raises(MappingError, match="no Nova tenant mapping"):
        map_legacy_row(
            "prospecting_campaigns",
            {"id": "pc_1", "tenant_id": 8, "created_by_user_id": 12},
            tenant_ids={"7": "tenant-formkok"},
            user_subjects={"12": "user-operator"},
        )
    with pytest.raises(MappingError, match="no Nova subject mapping"):
        map_legacy_row(
            "prospecting_campaigns",
            {"id": "pc_1", "tenant_id": 7, "created_by_user_id": 99},
            tenant_ids={"7": "tenant-formkok"},
            user_subjects={"12": "user-operator"},
        )


def test_database_manifest_is_metadata_only_and_never_overwrites(tmp_path: Path):
    database = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO prospecting_campaigns (id, tenant_id, created_by_subject, name, status, mode, min_score, daily_limit, criteria_json, source_provider) "
                "VALUES ('pc_1', 'tenant-1', 'subject-1', 'Campaign', 'draft', 'manual_review', 65, 20, '{}', 'manual')"
            )
    finally:
        engine.dispose()
    manifest = manifest_from_database(f"sqlite:///{database}")
    assert manifest["tables"]["prospecting_campaigns"]["count"] == 1
    assert manifest["tables"]["website_prospects"]["count"] == 0
    output = tmp_path / "manifest.json"
    write_manifest(f"sqlite:///{database}", output)
    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    with pytest.raises(ManifestError, match="refusing to overwrite"):
        write_manifest(f"sqlite:///{database}", output)
    with pytest.raises(ManifestError, match="does not exist"):
        manifest_from_database(f"sqlite:///{tmp_path / 'missing.db'}")


def test_initial_migration_creates_only_nova_owned_tables(tmp_path: Path):
    database = tmp_path / "nova-gate-c.db"
    env = {**os.environ, "NOVA_DATABASE_URL": f"sqlite:///{database}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{database}")
    try:
        names = set(inspect(engine).get_table_names())
        columns = {column["name"] for column in inspect(engine).get_columns("website_proposals")}
    finally:
        engine.dispose()
    # Nova owns the six reconciled tables plus its audit trail, and nothing else.
    assert names == {*NOVA_OWNED_TABLES, "alembic_version"}
    assert "tenants" not in names
    assert "users" not in names
    assert "delivery_processed_at" in columns

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "downgrade", "base"],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    engine = create_engine(f"sqlite:///{database}")
    try:
        assert not (set(NOVA_OWNED_TABLES) & set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()
