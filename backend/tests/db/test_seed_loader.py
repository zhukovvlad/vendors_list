"""Интеграция loader.execute против реальной схемы (триггеры/uq-индексы/freeze).
db-тест: гоняется на тест-ветке Neon, скипается без DATABASE_URL_TEST."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.seed.loader import ListingRow, LoadPlan, PositionRow, execute
from app.seed.parse import CategoryNode, SeedError
from app.seed.report import RunReport
from tests import factories as f

pytestmark = pytest.mark.db


def _mini_plan() -> LoadPlan:
    cats = [CategoryNode((1,), "Оборудование", None, 1)]
    positions = [PositionRow(1, (1,), "Насос", "1", 0)]
    listings = [
        ListingRow(1, "residential", "Бизнес", "allowed", "Ридан", False, None, None, 0),
        ListingRow(1, "residential", "Бизнес", "allowed", "ТеплоСила", False, None, None, 1),
    ]
    vendors = {"Ридан": False, "ТеплоСила": True}
    report = RunReport(files=[], vendors_unique=2, agreements=1,
                       star_occurrences=1, categories=1, category_warnings=[])
    return LoadPlan(cats, positions, listings, vendors, {"residential": "2026-03-25"}, report)


async def test_execute_loads_and_attributes_author(db_conn) -> None:
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    rows = (await db_conn.execute(
        text("SELECT created_by FROM listing WHERE status = 'allowed'"))).scalars().all()
    assert len(rows) == 2 and set(rows) == {"seed@test"}  # автор через триггер
    starred = (await db_conn.execute(
        text("SELECT vendor_starred(id) FROM vendor WHERE name = 'ТеплоСила'"))).scalar_one()
    assert starred is True  # звезда → agreement.active → vendor_starred


async def test_execute_guard_blocks_when_projects_exist(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await f.make_project(db_conn, code="P-guard", name="Проект", segment_id=seg)
    with pytest.raises(SeedError, match="проектами"):
        await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)


async def test_force_does_not_touch_projects(db_conn) -> None:
    # §14: --force снимает guard, но проект (без ссылок на удаляемые строки) выживает
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    proj = await f.make_project(db_conn, code="P-force", name="Проект", segment_id=seg)
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=True)
    survived = (await db_conn.execute(
        text("SELECT count(*) FROM compliance.project WHERE id = :p"), {"p": proj})).scalar_one()
    assert survived == 1


async def test_force_cannot_delete_standards_referenced_by_selection(db_conn) -> None:
    # Если выбор проекта ссылается на вендора/позицию — DELETE ядра падает на FK,
    # транзакция откатывается: снести стандарты «из-под» проекта нельзя даже с --force.
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="X")
    pos = await f.make_position(db_conn, category_id=cat, name="Поз")
    v = await f.make_vendor(db_conn, name="V-keep")
    proj = await f.make_project(db_conn, code="P-ref", name="Проект", segment_id=seg)
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=v)
    with pytest.raises(DBAPIError):  # FK RESTRICT на vendor/position
        await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=True)


async def test_execute_is_idempotent(db_conn) -> None:
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    n1 = (await db_conn.execute(text("SELECT count(*) FROM listing"))).scalar_one()
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    n2 = (await db_conn.execute(text("SELECT count(*) FROM listing"))).scalar_one()
    assert n1 == n2  # reset+reload — повтор не плодит строки


async def test_execute_freeze_publishes_snapshot(db_conn) -> None:
    # закрывает замечание №4: freeze-путь под автотестом
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=True, force=False)
    rel = (await db_conn.execute(text(
        "SELECT id, status FROM release WHERE building_type_id = "
        "(SELECT id FROM building_type WHERE code = 'residential') "
        "ORDER BY id DESC LIMIT 1"))).mappings().one()
    assert rel["status"] == "published"
    snap = (await db_conn.execute(
        text("SELECT vendor_name FROM release_listing WHERE release_id = :r"),
        {"r": rel["id"]})).scalars().all()
    assert "Ридан" in snap
