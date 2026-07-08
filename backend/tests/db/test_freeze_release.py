"""freeze_release: копирует живой перечень в снимок и публикует; повторный
вызов на уже зафиксированном релизе — исключение (инвариант БД)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests import factories as f

pytestmark = pytest.mark.db


async def test_freeze_copies_and_publishes(db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Freeze-V")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rel = await f.make_release(db_conn, building_type_id=bt, label="ред.1", status="open")

    await db_conn.execute(text("SELECT freeze_release(:r, :a)"), {"r": rel, "a": "editor@test"})

    status_ = (
        await db_conn.execute(text("SELECT status FROM release WHERE id = :r"), {"r": rel})
    ).scalar_one()
    assert status_ == "published"

    snap = (
        await db_conn.execute(
            text("SELECT * FROM release_listing WHERE release_id = :r"), {"r": rel}
        )
    ).mappings().all()
    # Проверяем НАЛИЧИЕ созданной строки, а не общий счётчик: когда появятся
    # боевые листинги (импорт — этап 5), data+schema-ветка их унаследует и
    # residential-снимок может стать больше единицы.
    by_vendor = {r["vendor_name"]: r for r in snap}
    assert "Freeze-V" in by_vendor
    assert by_vendor["Freeze-V"]["vendor_starred"] is True


async def test_freeze_twice_raises(db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="social")
    rel = await f.make_release(db_conn, building_type_id=bt, label="ред.2", status="open")
    await db_conn.execute(text("SELECT freeze_release(:r, NULL)"), {"r": rel})
    # Повторный вызов — статус уже 'published' → RAISE EXCEPTION в функции.
    # Это последняя операция теста: транзакция уходит в aborted, но db_conn
    # всё равно откатывается в teardown (см. spec §5 про SAVEPOINT).
    with pytest.raises(DBAPIError):
        await db_conn.execute(text("SELECT freeze_release(:r, NULL)"), {"r": rel})
