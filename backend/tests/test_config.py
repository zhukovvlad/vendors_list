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


def test_database_url_test_normalizes_raw_neon_url() -> None:
    """CI получает от Neon сырой libpq-URI без +asyncpg и с libpq ssl-параметрами."""
    s = Settings(
        database_url_test="postgresql://u:p@host/db?sslmode=require&channel_binding=require"
    )
    assert s.database_url_test == "postgresql+asyncpg://u:p@host/db?ssl=require"
    assert s.database_url_test_sync == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_database_url_test_normalization_is_idempotent() -> None:
    s = Settings(database_url_test="postgresql+asyncpg://u:p@host/db?ssl=require")
    assert s.database_url_test == "postgresql+asyncpg://u:p@host/db?ssl=require"


def test_database_url_normalizes_raw_neon_url() -> None:
    """Сырой libpq-URI из Neon (postgres://…?sslmode=&channel_binding=) → async-вид
    для asyncpg: +asyncpg, sslmode→ssl, channel_binding выкинут."""
    s = Settings(
        database_url="postgresql://u:p@host/db?sslmode=require&channel_binding=require"
    )
    assert s.database_url == "postgresql+asyncpg://u:p@host/db?ssl=require"


def test_database_url_normalization_idempotent() -> None:
    s = Settings(database_url="postgresql+asyncpg://u:p@host/db?ssl=require")
    assert s.database_url == "postgresql+asyncpg://u:p@host/db?ssl=require"


def test_database_url_localhost_no_ssl_preserved() -> None:
    """Локальный dev без SSL: ssl НЕ навязываем (иначе не-SSL Postgres откажет
    в подключении) — в отличие от тест-URL, который всегда Neon."""
    s = Settings(
        database_url="postgresql+asyncpg://vendors:vendors@localhost:5432/vendors"
    )
    assert (
        s.database_url == "postgresql+asyncpg://vendors:vendors@localhost:5432/vendors"
    )


def test_database_url_sync_from_normalized_neon() -> None:
    """Sync-URL для Alembic выводится из нормализованного async-URL."""
    s = Settings(
        database_url="postgresql://u:p@host/db?sslmode=require&channel_binding=require"
    )
    assert s.database_url_sync == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_dashboard_stale_days_default() -> None:
    from app.config import Settings

    assert Settings().dashboard_stale_days == 14


def test_dashboard_stale_days_from_env(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("DASHBOARD_STALE_DAYS", "7")
    assert Settings().dashboard_stale_days == 7
