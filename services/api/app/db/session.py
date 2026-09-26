"""Local SQLAlchemy session setup; Nova owns this database."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_options(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        # SQLite is the local/dev and single-container default; the pool tuning
        # below only applies to real server databases.
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
        "pool_pre_ping": True,
    }


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or settings.DATABASE_URL
    return create_engine(url, **_engine_options(url))


engine: Engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Request-scoped session that never leaks an open transaction."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
