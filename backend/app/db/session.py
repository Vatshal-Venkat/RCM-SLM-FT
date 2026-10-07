"""Database engine and session management (PostgreSQL / Neon in production, SQLite locally)."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    url = s.database_url
    kwargs: dict = {"echo": s.database_echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Serverless Postgres (Neon) drops idle connections; validate before use.
        kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"
