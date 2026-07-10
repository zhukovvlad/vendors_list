"""Вьюхи дашборда: dashboard_summary (агрегаты) и dashboard_open_drafts.

Вьюхи глобальны (считают ВСЮ базу) — тестируем ДЕЛЬТУ от базовой линии на
свежесозданных данных, а не абсолютные числа (БД засеяна)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _summary(db_conn) -> dict:
    return (
        (await db_conn.execute(text("SELECT * FROM dashboard_summary"))).mappings().one()
    )


async def test_positions_active_from_latest_published_snapshot(db_conn) -> None:
    base = (await _summary(db_conn))["positions_active"]
    bt = await f.make_building_type(db_conn, code="pa-bt")
    cat = await f.make_category(db_conn, name="pa-cat")
    p1 = await f.make_position(db_conn, category_id=cat, name="pa-p1")
    p2 = await f.make_position(db_conn, category_id=cat, name="pa-p2")
    rid = await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release_listing(db_conn, release_id=rid, position_id=p1)
    await f.make_release_listing(db_conn, release_id=rid, position_id=p2)
    await f.make_release_listing(db_conn, release_id=rid, position_id=p2)  # дубль → distinct=2
    assert (await _summary(db_conn))["positions_active"] == base + 2


async def test_latest_published_deterministic_on_equal_dates(db_conn) -> None:
    # Два published с ОДИНАКОВОЙ датой; побеждает больший id (страховка детерминизма).
    base = (await _summary(db_conn))["positions_active"]
    bt = await f.make_building_type(db_conn, code="det-bt")
    cat = await f.make_category(db_conn, name="det-cat")
    p_old = await f.make_position(db_conn, category_id=cat, name="det-old")
    p_extra = await f.make_position(db_conn, category_id=cat, name="det-extra")
    p_new = await f.make_position(db_conn, category_id=cat, name="det-new")
    r1 = await f.make_release(db_conn, building_type_id=bt, status="published")
    r2 = await f.make_release(db_conn, building_type_id=bt, status="published")
    await db_conn.execute(
        text("UPDATE release SET effective_date = DATE '2026-01-01' WHERE id IN (:a, :b)"),
        {"a": r1, "b": r2},
    )
    await f.make_release_listing(db_conn, release_id=r1, position_id=p_old)
    await f.make_release_listing(db_conn, release_id=r1, position_id=p_extra)  # r1 → 2
    await f.make_release_listing(db_conn, release_id=r2, position_id=p_new)     # r2 → 1
    # r2.id > r1.id ⇒ выбран r2 ⇒ этот тип даёт 1, не 2.
    assert (await _summary(db_conn))["positions_active"] == base + 1


async def test_vendors_brandkey_and_agreement(db_conn) -> None:
    base = await _summary(db_conn)
    owner = await f.make_vendor(db_conn, name="BK-Owner")
    await f.make_vendor(db_conn, name="BK-Sub", represents_id=owner)  # тот же бренд
    after_add = await _summary(db_conn)
    assert after_add["vendors_total"] == base["vendors_total"] + 1  # sub схлопнут
    assert after_add["vendors_with_agreement"] == base["vendors_with_agreement"]
    await f.make_agreement(db_conn, vendor_id=owner, status="active")
    after_agr = await _summary(db_conn)
    assert after_agr["vendors_with_agreement"] == base["vendors_with_agreement"] + 1


async def test_release_status_counts_exclude_archived(db_conn) -> None:
    base = await _summary(db_conn)
    bt = await f.make_building_type(db_conn, code="rc-bt")
    await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release(db_conn, building_type_id=bt, status="open")
    await f.make_release(db_conn, building_type_id=bt, status="archived")
    after = await _summary(db_conn)
    assert after["releases_published"] == base["releases_published"] + 1
    assert after["drafts_open"] == base["drafts_open"] + 1  # archived НЕ считается


async def test_open_drafts_only_open_visible(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od-bt")
    rid_pub = await f.make_release(db_conn, building_type_id=bt, status="published")
    rid_open = await f.make_release(db_conn, building_type_id=bt, status="open")
    ids = {
        r["release_id"]
        for r in (
            await db_conn.execute(text("SELECT release_id FROM dashboard_open_drafts"))
        ).mappings()
    }
    assert rid_open in ids and rid_pub not in ids


async def test_open_drafts_last_touched_fallback_to_created_at(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od2-bt")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")  # без правок listing
    row = (
        await db_conn.execute(
            text("SELECT last_touched_at FROM dashboard_open_drafts WHERE release_id = :r"),
            {"r": rid},
        )
    ).mappings().one()
    assert row["last_touched_at"] is not None  # fallback = release.created_at


async def test_open_drafts_last_touched_from_listing(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od3-bt")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="od3-seg")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")
    cat = await f.make_category(db_conn, name="od3-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="od3-pos")
    v = await f.make_vendor(db_conn, name="od3-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    row = (
        await db_conn.execute(
            text(
                "SELECT last_touched_at, last_touched_by "
                "FROM dashboard_open_drafts WHERE release_id = :r"
            ),
            {"r": rid},
        )
    ).mappings().one()
    assert row["last_touched_at"] is not None
    assert row["last_touched_by"] is not None  # current_app_user() из вставки listing
