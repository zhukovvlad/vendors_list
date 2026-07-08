"""listing_live: звезда вендора (по активному соглашению), путь раздела,
мета-строка requirement. Логика в БД — ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def test_star_and_category_path(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    root = await f.make_category(db_conn, name="Оборудование")
    cat = await f.make_category(db_conn, name="ОВиК", parent_id=root)
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Grundfos-T")
    await f.make_agreement(db_conn, vendor_id=v, status="active")  # ставит звезду
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )

    row = (
        await db_conn.execute(
            text("SELECT * FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).mappings().one()
    assert row["vendor_starred"] is True
    assert row["category_path"] == "Оборудование / ОВиК"
    assert row["vendor_name"] == "Grundfos-T"


async def test_no_star_without_active_agreement(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Комфорт")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="NoStar-V")
    await f.make_agreement(db_conn, vendor_id=v, status="expired")  # НЕ активно
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )
    starred = (
        await db_conn.execute(
            text("SELECT vendor_starred FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).scalar_one()
    assert starred is False


async def test_requirement_meta_row(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="Сантехника")
    pos = await f.make_position(db_conn, category_id=cat, name="Смесители")
    lid = await f.make_listing(
        db_conn,
        position_id=pos,
        segment_id=seg,
        vendor_id=None,
        status="requirement",
        spec_text="Россия",
    )
    row = (
        await db_conn.execute(
            text("SELECT * FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).mappings().one()
    assert row["status"] == "requirement"
    assert row["vendor_starred"] is False
    assert row["spec_text"] == "Россия"
    assert row["vendor_name"] is None
