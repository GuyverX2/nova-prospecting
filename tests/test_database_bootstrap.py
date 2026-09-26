"""An auto-created database must still be upgradable by Alembic.

The bug this pins: starting the app against an empty volume created every
table via ``create_all`` but left ``alembic_version`` empty, so the next
release's ``alembic upgrade head`` aborted with "table already exists" and the
deployment could not move forward.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.db.bootstrap import alembic_config, current_revision, ensure_schema
from app.db.session import Base


def _engine(tmp_path, name="nova.db"):
    return create_engine(f"sqlite:///{tmp_path / name}", connect_args={"check_same_thread": False})


def test_auto_created_database_is_stamped_at_head(tmp_path):
    engine = _engine(tmp_path)
    assert ensure_schema(engine) == "created"

    tables = set(inspect(engine).get_table_names())
    assert {"website_prospects", "website_analyses", "audit_events"} <= tables
    assert current_revision(engine) is not None, "a created schema must carry its revision"

    # The decisive assertion: alembic accepts the database it did not create.
    command.upgrade(alembic_config(str(engine.url)), "head")
    assert ensure_schema(engine) == "managed"
    engine.dispose()


def test_migrated_database_is_left_alone(tmp_path):
    engine = _engine(tmp_path, "migrated.db")
    command.upgrade(alembic_config(str(engine.url)), "head")
    assert ensure_schema(engine) == "managed"
    engine.dispose()


def test_legacy_unstamped_schema_is_reported_not_guessed(tmp_path):
    """Databases from before the stamping fix must not be silently mislabelled."""
    engine = _engine(tmp_path, "legacy.db")
    Base.metadata.create_all(engine)
    assert current_revision(engine) is None

    assert ensure_schema(engine) == "unstamped"
    assert current_revision(engine) is None, "we must not claim a revision we cannot prove"
    engine.dispose()


def test_migrations_produce_the_same_tables_as_the_models(tmp_path):
    created = _engine(tmp_path, "created.db")
    migrated = _engine(tmp_path, "migrated.db")
    ensure_schema(created)
    command.upgrade(alembic_config(str(migrated.url)), "head")

    def schema(engine):
        inspector = inspect(engine)
        return {
            table: sorted(column["name"] for column in inspector.get_columns(table))
            for table in inspector.get_table_names()
            if table != "alembic_version"
        }

    assert schema(created) == schema(migrated)
    created.dispose()
    migrated.dispose()


@pytest.mark.parametrize("revision", ["base", "head"])
def test_migrations_round_trip(tmp_path, revision):
    engine = _engine(tmp_path, f"round-{revision}.db")
    config = alembic_config(str(engine.url))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, revision if revision != "base" else "head")
    assert inspect(engine).get_table_names()
    engine.dispose()
