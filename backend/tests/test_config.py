from app.config import Settings


def test_database_url_test_sync_derivation() -> None:
    s = Settings(
        database_url_test="postgresql+asyncpg://u:p@host/db?ssl=require"
    )
    assert s.database_url_test_sync == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_database_url_test_defaults_empty() -> None:
    s = Settings(database_url_test="")
    assert s.database_url_test == ""
    assert s.database_url_test_sync == ""
