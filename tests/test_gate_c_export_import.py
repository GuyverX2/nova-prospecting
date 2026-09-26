from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.db.session import Base
from app.prospecting import models  # noqa: F401 -- registers the six target tables
from scripts.gate_c.export_import import ExportImportError, export_import
from scripts.gate_c.manifest import manifest_from_database
from scripts.gate_c.reconcile import TABLES, _read_manifest, reconcile


@pytest.fixture()
def source_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'source.db'}"
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE prospecting_campaigns (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                "created_by_user_id TEXT, name TEXT, status TEXT, mode TEXT, min_score INTEGER, "
                "daily_limit INTEGER, criteria_json TEXT, source_provider TEXT)"
            )
            for name in TABLES[1:]:
                connection.exec_driver_sql(
                    f'CREATE TABLE "{name}" (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL)'
                )
            connection.exec_driver_sql(
                "INSERT INTO prospecting_campaigns (id, tenant_id, created_by_user_id, name, status, mode, "
                "min_score, daily_limit, criteria_json, source_provider) "
                "VALUES ('pc_1', '7', '12', 'Campaign', 'active', 'manual_review', 65, 20, '{}', 'manual')"
            )
    finally:
        engine.dispose()
    return url


@pytest.fixture()
def target_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'target.db'}"
    engine = create_engine(url)
    try:
        tables = [Base.metadata.tables[name] for name in TABLES]
        Base.metadata.create_all(engine, tables=tables)
    finally:
        engine.dispose()
    return url


def test_export_import_rehearsal_is_fail_closed_and_tenant_preserving(
    source_db: str, target_db: str, tmp_path: Path
):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps({"tenant_ids": {"7": "tenant-formkok"}, "user_subjects": {"12": "subject-operator"}}),
        encoding="utf-8",
    )
    output = tmp_path / "target-manifest.json"
    counts = export_import(
        source_url=source_db,
        target_url=target_db,
        mapping=mapping,
        output_manifest=output,
    )
    assert counts["prospecting_campaigns"] == 1

    manifest = _read_manifest(output)
    assert manifest["tables"]["prospecting_campaigns"]["count"] == 1


    source = manifest_from_database(source_db, tenant_ids={"7": "tenant-formkok"})
    assert reconcile(source, manifest) == counts


@pytest.fixture()
def source_db_reattrib(tmp_path: Path) -> str:
    """Source with a campaign row whose owner (user 3) is NOT in user_subjects."""
    url = f"sqlite:///{tmp_path / 'source-reattrib.db'}"
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE prospecting_campaigns (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                "created_by_user_id TEXT, name TEXT, status TEXT, mode TEXT, min_score INTEGER, "
                "daily_limit INTEGER, criteria_json TEXT, source_provider TEXT)"
            )
            for name in TABLES[1:]:
                connection.exec_driver_sql(
                    f'CREATE TABLE "{name}" (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL)'
                )
            connection.exec_driver_sql(
                "INSERT INTO prospecting_campaigns (id, tenant_id, created_by_user_id, name, status, mode, "
                "min_score, daily_limit, criteria_json, source_provider) "
                "VALUES ('pc_r', '7', '3', 'Reattrib', 'active', 'manual_review', 65, 20, '{}', 'manual')"
            )
    finally:
        engine.dispose()
    return url


def test_export_import_reattributes_unmapped_owner_to_mapped_subject(
    source_db_reattrib: str, target_db: str, tmp_path: Path
):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "tenant_ids": {"7": "tenant-formkok"},
                "user_subjects": {"2": "subject-admin"},
                "subject_reattributions": {"3": "2"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "target-manifest.json"
    counts = export_import(
        source_url=source_db_reattrib,
        target_url=target_db,
        mapping=mapping,
        output_manifest=output,
    )
    assert counts["prospecting_campaigns"] == 1

    engine = create_engine(target_db)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                __import__("sqlalchemy").text(
                    "select id, tenant_id, created_by_subject from prospecting_campaigns"
                )
            ).mappings().first()
    finally:
        engine.dispose()
    assert row["id"] == "pc_r"
    assert row["tenant_id"] == "tenant-formkok"
    assert row["created_by_subject"] == "subject-admin"


def test_export_import_reattribution_requires_valid_target(
    source_db_reattrib: str, target_db: str, tmp_path: Path
):
    bad_target = tmp_path / "bad-target.json"
    bad_target.write_text(
        json.dumps(
            {
                "tenant_ids": {"7": "tenant-formkok"},
                "user_subjects": {"2": "subject-admin"},
                "subject_reattributions": {"3": "99"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExportImportError, match="must be present in user_subjects"):
        export_import(
            source_url=source_db_reattrib,
            target_url=target_db,
            mapping=bad_target,
            output_manifest=tmp_path / "m0.json",
        )
    conflicting = tmp_path / "conflicting.json"
    conflicting.write_text(
        json.dumps(
            {
                "tenant_ids": {"7": "tenant-formkok"},
                "user_subjects": {"3": "subject-3", "2": "subject-admin"},
                "subject_reattributions": {"3": "2"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExportImportError, match="must not also be in user_subjects"):
        export_import(
            source_url=source_db_reattrib,
            target_url=target_db,
            mapping=conflicting,
            output_manifest=tmp_path / "m1.json",
        )


def test_export_import_refuses_overlap_and_missing_mapping(
    source_db: str, target_db: str, tmp_path: Path
):
    with pytest.raises(ExportImportError, match="different credentials"):
        export_import(
            source_url=source_db,
            target_url=source_db,
            mapping=tmp_path / "mapping.json",
            output_manifest=tmp_path / "manifest0.json",
        )
    with pytest.raises(ExportImportError, match="cannot read mapping file"):
        export_import(
            source_url=source_db,
            target_url=target_db,
            mapping=tmp_path / "missing.json",
            output_manifest=tmp_path / "manifest1.json",
        )
