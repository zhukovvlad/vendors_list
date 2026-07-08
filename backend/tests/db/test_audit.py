"""Аудит подписывается логином из app.user (SET LOCAL в транзакции).
Логика уже в БД (триггеры *_audit + current_app_user); ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def test_agreement_audit_records_app_user(db_conn) -> None:
    await db_conn.execute(
        text("SELECT set_config('app.user', :u, true)"), {"u": "alice@test"}
    )
    vid = await f.make_vendor(db_conn, name="Audit-Vendor")
    aid = await f.make_agreement(db_conn, vendor_id=vid, status="active")

    changed_by = (
        await db_conn.execute(
            text(
                "SELECT changed_by FROM agreement_change_log "
                "WHERE agreement_id = :a AND action = 'insert'"
            ),
            {"a": aid},
        )
    ).scalar_one()
    assert changed_by == "alice@test"


async def test_listing_created_by_defaults_to_app_user(db_conn) -> None:
    await db_conn.execute(
        text("SELECT set_config('app.user', :u, true)"), {"u": "bob@test"}
    )
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Audit-Listing-V")
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )
    created_by = (
        await db_conn.execute(
            text("SELECT created_by FROM listing WHERE id = :i"), {"i": lid}
        )
    ).scalar_one()
    assert created_by == "bob@test"
