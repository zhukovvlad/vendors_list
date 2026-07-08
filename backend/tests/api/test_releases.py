"""POST /releases/{id}/freeze (admin) → снимок в release_listing; 409 на unknown."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_freeze_via_api(client, as_admin, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Премиум")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="RelAPI-V")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rel = await f.make_release(db_conn, building_type_id=bt, label="API-ред", status="open")

    resp = await client.post(f"/releases/{rel}/freeze")
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    snap = await client.get(f"/releases/{rel}/listing")
    assert snap.status_code == 200
    # Наличие созданной строки, не общий счётчик (см. пояснение в db-тесте freeze).
    assert any(r["vendor_name"] == "RelAPI-V" for r in snap.json())


async def test_freeze_unknown_release_409(client, as_admin) -> None:
    resp = await client.post("/releases/999999/freeze")
    assert resp.status_code == 409


async def test_freeze_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="social")
    rel = await f.make_release(db_conn, building_type_id=bt, label="V-ред", status="open")
    resp = await client.post(f"/releases/{rel}/freeze")
    assert resp.status_code == 403
