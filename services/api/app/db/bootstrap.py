"""Create the schema for a fresh database without orphaning it from Alembic.

``Base.metadata.create_all()`` is convenient for local runs and the single
container image, but on its own it produces a database that Alembic does not
recognise: the tables exist and ``alembic_version`` is empty, so the next
``alembic upgrade head`` dies with "table already exists" and the deployment is
stuck. Every auto-created schema is therefore stamped at the current head in
the same step, which is exactly what a hand-run migration would have left
behind.

A database that already carries tables is never touched here — once it exists,
migrations own it.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.session import Base

logger = logging.getLogger("nova.db")

#: services/api/alembic — resolved from this file so it works in the container
#: image and in a source checkout without a configuration file.
ALEMBIC_DIRECTORY = Path(__file__).resolve().parents[2] / "alembic"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIRECTORY))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def ensure_schema(engine: Engine) -> str:
    """Return what was done: ``created``, ``stamped`` or ``managed``."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    revision = current_revision(engine) if "alembic_version" in tables else None

    if revision:
        # Alembic already owns this database.
        return "managed"

    if tables - {"alembic_version"}:
        # Tables from an older auto-create, before this stamping existed. We
        # cannot know which revision that schema corresponds to, so guessing
        # would risk skipping a migration: say so and let an operator decide.
        logger.warning(
            "nova_db_unstamped",
            extra={"tables": len(tables), "hint": "run `alembic stamp <revision>` once, then upgrade"},
        )
        return "unstamped"

    Base.metadata.create_all(engine)
    command.stamp(alembic_config(str(engine.url.render_as_string(hide_password=False))), "head")
    logger.info("nova_db_created", extra={"tables": len(inspect(engine).get_table_names())})
    return "created"
