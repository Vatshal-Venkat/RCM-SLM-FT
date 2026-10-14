import pytest

from app.core.config import Settings


@pytest.mark.parametrize("url", [
    "postgres://u:p@ep-x.neon.tech/db?sslmode=require",
    "postgresql://u:p@ep-x.neon.tech/db?sslmode=require",
])
def test_neon_urls_use_psycopg3_driver(url):
    s = Settings(_env_file=None, database_url=url)
    assert s.database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"


@pytest.mark.parametrize("url", ["sqlite:///data/rcm.db", "postgresql+psycopg://u:p@h/db"])
def test_explicit_urls_are_unchanged(url):
    assert Settings(_env_file=None, database_url=url).database_url == url


def test_cors_origins_from_json_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://rcm.vercel.app"]')
    assert Settings(_env_file=None).cors_origins == ["https://rcm.vercel.app"]
