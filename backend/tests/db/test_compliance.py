"""Светофор compliance.project_position_status и процент project_summary.
Логика в БД — ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _state(db_conn, project_id: int, position_id: int) -> str:
    return (
        await db_conn.execute(
            text(
                "SELECT position_state FROM compliance.project_position_status "
                "WHERE project_id = :p AND position_id = :pos"
            ),
            {"p": project_id, "pos": position_id},
        )
    ).scalar_one()


async def _project_with_allowed(db_conn, seg_name: str, code: str):
    """Проект на классе seg_name + позиция со стандартом (allowed=vendor A)."""
    seg = await f.get_segment_id(db_conn, name=seg_name)
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    allowed = await f.make_vendor(db_conn, name=f"Allowed-{code}")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=allowed, status="allowed"
    )
    proj = await f.make_project(db_conn, code=code, name="Проект", segment_id=seg)
    return seg, pos, allowed, proj


async def test_compliant(db_conn) -> None:
    _, pos, allowed, proj = await _project_with_allowed(db_conn, "Бизнес", "C-1")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=allowed)
    assert await _state(db_conn, proj, pos) == "compliant"


async def test_deviation(db_conn) -> None:
    _, pos, _allowed, proj = await _project_with_allowed(db_conn, "Премиум", "C-2")
    off = await f.make_vendor(db_conn, name="Off-Standard-V")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=off)
    assert await _state(db_conn, proj, pos) == "deviation"


async def test_open(db_conn) -> None:
    _, pos, _allowed, proj = await _project_with_allowed(db_conn, "Комфорт", "C-3")
    assert await _state(db_conn, proj, pos) == "open"


async def test_manual_check_requirement_only(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="Сантехника")
    pos = await f.make_position(db_conn, category_id=cat, name="Трубы")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=None,
        status="requirement", spec_text="ГОСТ",
    )
    proj = await f.make_project(db_conn, code="C-4", name="Проект", segment_id=seg)
    v = await f.make_vendor(db_conn, name="Any-V")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=v)
    assert await _state(db_conn, proj, pos) == "manual_check"


async def test_compliance_pct_50(db_conn) -> None:
    """1 compliant + 1 deviation → 50.0%."""
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    proj = await f.make_project(db_conn, code="C-5", name="Проект", segment_id=seg)

    pos_ok = await f.make_position(db_conn, category_id=cat, name="Насосы")
    a1 = await f.make_vendor(db_conn, name="Pct-Allowed-1")
    await f.make_listing(
        db_conn, position_id=pos_ok, segment_id=seg, vendor_id=a1, status="allowed",
    )
    await f.make_selection(db_conn, project_id=proj, position_id=pos_ok, vendor_id=a1)

    pos_dev = await f.make_position(db_conn, category_id=cat, name="Клапаны")
    a2 = await f.make_vendor(db_conn, name="Pct-Allowed-2")
    off = await f.make_vendor(db_conn, name="Pct-Off")
    await f.make_listing(
        db_conn, position_id=pos_dev, segment_id=seg, vendor_id=a2, status="allowed",
    )
    await f.make_selection(db_conn, project_id=proj, position_id=pos_dev, vendor_id=off)

    pct = (
        await db_conn.execute(
            text("SELECT compliance_pct FROM compliance.project_summary WHERE project_id = :p"),
            {"p": proj},
        )
    ).scalar_one()
    assert float(pct) == 50.0


async def test_compliant_via_brand_key(db_conn) -> None:
    """Вендор-представитель разрешённого бренда = compliant, НЕ deviation.
    Вьюха судит по brand_key = coalesce(represents_id, id): выбор ИСТРАТЕХ
    (represents -> Grundfos) при стандарте Grundfos засчитывается. Самое
    неочевидное правило слоя — «упрощение» brand_key прошло бы мимо остальных
    тестов зелёным."""
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    owner = await f.make_vendor(db_conn, name="Grundfos")  # бренд-владелец в стандарте
    rep = await f.make_vendor(db_conn, name="ИСТРАТЕХ", represents_id=owner)  # представитель
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=owner, status="allowed"
    )
    proj = await f.make_project(db_conn, code="C-6", name="Проект", segment_id=seg)
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=rep)

    off = (
        await db_conn.execute(
            text(
                "SELECT off_standard_count FROM compliance.project_position_status "
                "WHERE project_id = :p AND position_id = :pos"
            ),
            {"p": proj, "pos": pos},
        )
    ).scalar_one()
    assert off == 0
    assert await _state(db_conn, proj, pos) == "compliant"
