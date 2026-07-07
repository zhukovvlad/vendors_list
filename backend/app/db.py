"""Слой доступа к БД: async-движок SQLAlchemy **Core** (не ORM).

Две FastAPI-зависимости:

* ``read_conn``  — соединение для чтения (без транзакционной идентичности).
* ``tx``        — транзакция с идентичностью: ПЕРВЫМ делом выставляет
  ``app.user`` через ``set_config(..., is_local => true)`` — это ровно
  семантика ``SET LOCAL`` (живёт только внутри текущей транзакции), поэтому
  при transaction pooling (PgBouncer) идентичность не протекает в чужой
  запрос и аудит в БД (``current_app_user()``) подписывается верным логином.

Значение логина передаётся ПАРАМЕТРОМ (bind), а не конкатенацией строки —
защита от инъекции в аудит.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .auth import CurrentUser, require_user
from .config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
            # За транзакционным пулером (PgBouncer / Neon -pooler) asyncpg-кэш
            # prepared statements ломается ("prepared statement already exists").
            # Отключаем его — безопасно и для прямого соединения (лишь мелкий
            # оверхед на повторных запросах).
            connect_args={"statement_cache_size": 0},
        )
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def read_conn() -> AsyncIterator[AsyncConnection]:
    """Соединение только для чтения. Транзакция закрывается по выходу."""
    async with get_engine().connect() as conn:
        yield conn


async def tx(user: CurrentUser = Depends(require_user)) -> AsyncIterator[AsyncConnection]:
    """Пишущая транзакция с идентичностью аудита.

    Открывает транзакцию, ПЕРВЫМ запросом фиксирует ``app.user`` (SET LOCAL
    через ``set_config``), затем отдаёт соединение. Коммит — при успехе,
    ROLLBACK — при исключении (гарантирует ``engine.begin()``).
    Все пишущие эндпоинты работают ТОЛЬКО через эту зависимость.
    """
    async with get_engine().begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.user', :app_user, true)"),
            {"app_user": user.username},
        )
        yield conn
