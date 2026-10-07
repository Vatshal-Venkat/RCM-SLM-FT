"""Test fixtures: an isolated SQLite database seeded with a small synthetic dataset."""

from __future__ import annotations

from datetime import date

import pytest

AS_OF = date(2026, 9, 30)


def _clear_caches() -> None:
    from app.core.config import get_settings
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    import os

    db_path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["LLM_LOAD_ON_STARTUP"] = "false"
    os.environ["RAG_LOAD_ON_STARTUP"] = "false"
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    _clear_caches()

    from app.db.init_db import create_schema, load_rows
    from app.db.session import get_engine
    from app.db.synthetic import generate

    create_schema(get_engine(), reset=True)
    data = generate(as_of=AS_OF, months=8, base_monthly_claims=150, seed=7)
    load_rows(get_engine(), data)
    yield data
    get_engine().dispose()
    _clear_caches()


@pytest.fixture
def db(seeded_db):
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as session:
        yield session
