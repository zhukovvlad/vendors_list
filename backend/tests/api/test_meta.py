"""Мета-справочники: /meta/positions для комбобокса «+ стандарт»."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_meta_positions_scoped_to_building_type(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="mp-bt")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="mp-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы дренажные")
    other = await f.make_position(db_conn, category_id=cat, name="Позиция-без-листинга")
    v = await f.make_vendor(db_conn, name="mp-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get(f"/meta/positions?building_type_id={bt}")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert "Насосы дренажные" in names       # есть живой листинг в этом типе
    assert "Позиция-без-листинга" not in names  # листинга нет → не в выборке
    _ = other  # noqa: F841 — намеренно не в результате


async def test_meta_positions_search(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="mp-q")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="mp-q-cat")
    p1 = await f.make_position(db_conn, category_id=cat, name="Насосы")
    p2 = await f.make_position(db_conn, category_id=cat, name="Радиаторы")
    v = await f.make_vendor(db_conn, name="mp-q-v")
    await f.make_listing(db_conn, position_id=p1, segment_id=seg, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=p2, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get(f"/meta/positions?building_type_id={bt}&q=насос")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"Насосы"}
