"""GET /listings поверх listing_live: пагинация и фильтр по segment_id."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_listings_page_and_filter(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="List-V")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get("/listings", params={"segment_id": seg})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["limit"] == 100 and body["offset"] == 0
    assert any(r["vendor_name"] == "List-V" for r in body["items"])
