"""category_sort_path: preorder по кураторскому sort_order, детерминизм при дублях.
Логика в БД — ждём PASS сразу (инвертированный TDD для db-тестов)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _csp(db_conn, cat_id: int) -> list[int]:
    return (
        await db_conn.execute(
            text("SELECT category_sort_path(:c)"), {"c": cat_id}
        )
    ).scalar_one()


async def test_preorder_by_sort_order_not_alphabet(db_conn) -> None:
    # Родитель, под ним "Вентиляция" (sort_order=2) и "ОВиК" (sort_order=1):
    # алфавит дал бы Вентиляцию первой, курация требует ОВиК первым.
    root = await f.make_category(db_conn, name="Оборудование")
    vent = await f.make_category(db_conn, name="Вентиляция", parent_id=root)
    ovik = await f.make_category(db_conn, name="ОВиК", parent_id=root)
    await db_conn.execute(text("UPDATE category SET sort_order = 2 WHERE id = :i"), {"i": vent})
    await db_conn.execute(text("UPDATE category SET sort_order = 1 WHERE id = :i"), {"i": ovik})

    csp_ovik = await _csp(db_conn, ovik)
    csp_vent = await _csp(db_conn, vent)
    assert csp_ovik < csp_vent  # ОВиК раньше Вентиляции по курации


async def test_deterministic_on_duplicate_sort_order(db_conn) -> None:
    # Два раздела под общим родителем с ОДИНАКОВЫМ sort_order → устойчивый
    # порядок по id (пара [sort_order, id]).
    root = await f.make_category(db_conn, name="Корень")
    a = await f.make_category(db_conn, name="A", parent_id=root)
    b = await f.make_category(db_conn, name="B", parent_id=root)
    await db_conn.execute(text("UPDATE category SET sort_order = 5 WHERE id IN (:a, :b)"), {"a": a, "b": b})
    csp_a = await _csp(db_conn, a)
    csp_b = await _csp(db_conn, b)
    assert csp_a < csp_b  # a.id < b.id → детерминировано, не случайно


async def test_parent_prefixes_child(db_conn) -> None:
    root = await f.make_category(db_conn, name="Корень")
    child = await f.make_category(db_conn, name="Лист", parent_id=root)
    csp_root = await _csp(db_conn, root)
    csp_child = await _csp(db_conn, child)
    assert csp_child[: len(csp_root)] == csp_root  # путь ребёнка начинается с пути родителя
