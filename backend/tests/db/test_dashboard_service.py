import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.services import dashboard as svc
from app.services.dashboard import count_merge_candidates
from tests import factories as f

pytestmark = pytest.mark.db


async def test_norm_collision_between_brands_is_candidate(db_conn) -> None:
    base = await count_merge_candidates(db_conn)
    await f.make_vendor(db_conn, name="ZzBrand")
    await f.make_vendor(db_conn, name="zzbrand")  # та же норма, другой бренд-ключ
    assert await count_merge_candidates(db_conn) == base + 1


async def test_linked_vendors_not_candidate(db_conn) -> None:
    base = await count_merge_candidates(db_conn)
    owner = await f.make_vendor(db_conn, name="YyBrand")
    await f.make_vendor(db_conn, name="yybrand", represents_id=owner)  # тот же бренд-ключ
    assert await count_merge_candidates(db_conn) == base  # не пара


async def test_local_statement_timeout_is_effective(db_conn) -> None:
    # Доказательство пункта ревью №1: SET LOCAL statement_timeout РЕАЛЬНО действует в
    # read-транзакции (db_conn уже в транзакции). Иначе защита в count_merge_candidates
    # была бы фикцией. 50 мс + pg_sleep(1) → отмена запроса.
    await db_conn.execute(text("SELECT set_config('statement_timeout', '50', true)"))
    with pytest.raises(DBAPIError):
        await db_conn.execute(text("SELECT pg_sleep(1)"))
    # транзакция после отмены — в aborted; фикстура db_conn откатит её в teardown.


async def test_returns_none_on_internal_db_error(db_conn, monkeypatch) -> None:
    # Пункт ревью №2: ВНУТРЕННЯЯ защита (except DBAPIError → None), а не только
    # роутерный except. SELECT vendor «падает» DBAPIError → функция сама вернёт None.
    orig = db_conn.execute
    state = {"n": 0}

    async def flaky(self, clause, *args, **kwargs):
        state["n"] += 1
        if state["n"] >= 2:  # 1-й вызов — set_config; 2-й — SELECT vendor → взрыв
            raise OperationalError("SELECT vendor", {}, Exception("simulated timeout"))
        return await orig(clause, *args, **kwargs)

    # AsyncConnection использует __slots__ (SQLAlchemy 2.0) — инстанс-атрибут "execute"
    # не назначить (AttributeError: read-only). Патчим метод на классе через monkeypatch
    # (тот сам восстановит оригинал в teardown), эффект — только для db_conn в этом тесте.
    # На классе flaky становится обычным методом → первым позиционным приходит self (=conn).
    monkeypatch.setattr(type(db_conn), "execute", flaky)
    assert await svc.count_merge_candidates(db_conn) is None
