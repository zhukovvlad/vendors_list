"""vendor_where_allowed: правило исключения (граница легитимности — релиз).

4 кейса ТЗ + детерминизм последнего релиза + порядок позиций. Изоляция —
свежий building_type на каждый тест (функция глобальна, но фильтр по вендору
и свежему типу делает результат детерминированным)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _rows(db_conn, vendor_id: int) -> list[dict]:
    return (
        await db_conn.execute(
            text("SELECT * FROM vendor_where_allowed(:v)"), {"v": vendor_id}
        )
    ).mappings().all()


async def test_allowed_when_live_and_released(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-a")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-a-seg")
    cat = await f.make_category(db_conn, name="wa-a-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-a-pos")
    v = await f.make_vendor(db_conn, name="wa-a-v")
    rid = await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release_listing(
        db_conn, release_id=rid, position_id=pos, segment_id=seg, vendor_id=v
    )
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["state"] == "allowed"
    assert rows[0]["release_label"] is None


async def test_excluded_when_released_but_not_live(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-b")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-b-seg")
    cat = await f.make_category(db_conn, name="wa-b-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-b-pos")
    v = await f.make_vendor(db_conn, name="wa-b-v")
    rid = await f.make_release(db_conn, building_type_id=bt, label="ред. B", status="published")
    await f.make_release_listing(
        db_conn, release_id=rid, position_id=pos, segment_id=seg, vendor_id=v
    )
    # живой строки НЕ создаём → был в релизе, сейчас исключён
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["state"] == "excluded"
    assert rows[0]["release_label"] == "ред. B"


async def test_draft_only_typo_not_shown(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-c")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-c-seg")
    cat = await f.make_category(db_conn, name="wa-c-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-c-pos")
    v = await f.make_vendor(db_conn, name="wa-c-v")
    # добавлен в живой и мягко удалён; в релиз не попадал
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )
    await db_conn.execute(text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid})
    assert await _rows(db_conn, v) == []


async def test_never_anywhere_not_shown(db_conn) -> None:
    v = await f.make_vendor(db_conn, name="wa-d-v")
    assert await _rows(db_conn, v) == []


async def test_excluded_label_from_latest_release_on_equal_dates(db_conn) -> None:
    # два published с равной датой; label берётся у победителя (больший id)
    bt = await f.make_building_type(db_conn, code="wa-det")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-det-seg")
    cat = await f.make_category(db_conn, name="wa-det-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-det-pos")
    v = await f.make_vendor(db_conn, name="wa-det-v")
    r1 = await f.make_release(db_conn, building_type_id=bt, label="старый", status="published")
    r2 = await f.make_release(db_conn, building_type_id=bt, label="новый", status="published")
    await db_conn.execute(
        text("UPDATE release SET effective_date = DATE '2026-01-01' WHERE id IN (:a, :b)"),
        {"a": r1, "b": r2},
    )
    await f.make_release_listing(
        db_conn, release_id=r1, position_id=pos, segment_id=seg, vendor_id=v
    )
    await f.make_release_listing(
        db_conn, release_id=r2, position_id=pos, segment_id=seg, vendor_id=v
    )
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["release_label"] == "новый"  # r2.id > r1.id


async def test_positions_ordered_by_category_sort_path(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-ord")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-ord-seg")
    # два раздела с разным sort_order → порядок позиций следует за деревом
    cat_b = await db_conn.execute(
        text("INSERT INTO category (name, sort_order) VALUES ('wa-ord-B', 2) RETURNING id")
    )
    cat_b_id = cat_b.scalar_one()
    cat_a = await db_conn.execute(
        text("INSERT INTO category (name, sort_order) VALUES ('wa-ord-A', 1) RETURNING id")
    )
    cat_a_id = cat_a.scalar_one()
    v = await f.make_vendor(db_conn, name="wa-ord-v")
    pos_b = await f.make_position(db_conn, category_id=cat_b_id, name="Б-позиция")
    pos_a = await f.make_position(db_conn, category_id=cat_a_id, name="А-позиция")
    await f.make_listing(db_conn, position_id=pos_b, segment_id=seg, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos_a, segment_id=seg, vendor_id=v, status="allowed")
    names = [r["position_name"] for r in await _rows(db_conn, v)]
    assert names == ["А-позиция", "Б-позиция"]  # sort_order 1 раньше 2
