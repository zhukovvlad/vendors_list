"""Фикстуры pytest для бэкенд-тестов.

db-тесты (маркер `db`) идут против тестовой ветки Neon (DATABASE_URL_TEST).
Если URL не задан — db-тесты пропускаются, чтобы локальный `just ci` без
тест-базы оставался зелёным. URL читаем через Settings (pydantic видит и .env,
и env-переменные CI), а не через os.getenv.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth import CurrentUser, require_user
from app.config import Settings, get_settings
from app.db import read_conn, tx
from app.main import app

TEST_DB_URL = get_settings().database_url_test


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if TEST_DB_URL:
        return
    skip_db = pytest.mark.skip(
        reason="DATABASE_URL_TEST не задан — интеграционные db-тесты пропущены"
    )
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Движок на тестовую ветку. NullPool — не держим соединения между тестами,
    заодно уходим от привязки пула к событийному циклу. statement_cache_size=0 —
    обязателен под транзакционный пулер Neon (как в app/db.py)."""
    eng = create_async_engine(
        TEST_DB_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Соединение в откатываемой транзакции: всё, что тест пишет, исчезает в конце."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db_conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент над приложением. read_conn/tx подменены на общее тест-соединение;
    tx-override дополнительно ставит app.user и оборачивает вызов в SAVEPOINT, чтобы
    пойманная роутером ошибка (409/404) откатывала только сбойную операцию, а не всю
    тест-транзакцию (spec §5)."""

    async def _override_read_conn():
        yield db_conn

    async def _override_tx(user: CurrentUser = Depends(require_user)):
        async with db_conn.begin_nested():  # SAVEPOINT
            await db_conn.execute(
                text("SELECT set_config('app.user', :u, true)"),
                {"u": user.username},
            )
            yield db_conn

    app.dependency_overrides[read_conn] = _override_read_conn
    app.dependency_overrides[tx] = _override_tx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    for dep in (read_conn, tx):
        app.dependency_overrides.pop(dep, None)


def _user_override(role: str, username: str):
    def _override() -> CurrentUser:
        return CurrentUser(username=username, role=role)

    return _override


@pytest.fixture
def as_admin() -> Iterator[CurrentUser]:
    app.dependency_overrides[require_user] = _user_override("admin", "admin@test")
    yield CurrentUser(username="admin@test", role="admin")
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture
def as_viewer() -> Iterator[CurrentUser]:
    app.dependency_overrides[require_user] = _user_override("viewer", "viewer@test")
    yield CurrentUser(username="viewer@test", role="viewer")
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture
def no_auth_bypass() -> Iterator[None]:
    """Выключить dev-bypass, чтобы require_user ушёл в реальную проверку токена
    (для теста 401). НЕ app_env='prod' — иначе lifespan кинет RuntimeError."""

    def _override() -> Settings:
        return Settings(auth_dev_bypass=False, app_env="dev")

    app.dependency_overrides[get_settings] = _override
    yield
    app.dependency_overrides.pop(get_settings, None)
