"""Карточка вендора: чтение шапки/дерева, мутации, RBAC."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_get_vendor_header(client, as_viewer, db_conn) -> None:
    owner = await f.make_vendor(db_conn, name="Owner-Co", kind="manufacturer")
    v = await f.make_vendor(db_conn, name="Sub-Co", kind="supplier", represents_id=owner)
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    await f.make_alias(db_conn, vendor_id=v, alias="SubCo")
    await f.make_vendor(db_conn, name="Sub-Co-2", represents_id=v)  # обратная ссылка на v

    resp = await client.get(f"/vendors/{v}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Sub-Co"
    assert body["kind"] == "supplier"
    assert body["starred"] is True
    assert body["represents"]["name"] == "Owner-Co"
    assert body["represented_count"] == 1
    assert [a["alias"] for a in body["aliases"]] == ["SubCo"]


async def test_get_vendor_404(client, as_viewer) -> None:
    resp = await client.get("/vendors/999999")
    assert resp.status_code == 404


async def test_where_allowed_tree(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-api")
    seg1 = await f.make_segment(db_conn, building_type_id=bt, name="Класс-1", sort_order=1)
    seg2 = await f.make_segment(db_conn, building_type_id=bt, name="Класс-2", sort_order=2)
    cat = await f.make_category(db_conn, name="wa-api-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-api-pos")
    v = await f.make_vendor(db_conn, name="wa-api-v")
    rid = await f.make_release(db_conn, building_type_id=bt, label="ред. API", status="published")
    # seg1 — жив (allowed); seg2 — был в релизе, живого нет (excluded)
    await f.make_release_listing(
        db_conn, release_id=rid, position_id=pos, segment_id=seg1, vendor_id=v
    )
    await f.make_release_listing(
        db_conn, release_id=rid, position_id=pos, segment_id=seg2, vendor_id=v
    )
    await f.make_listing(db_conn, position_id=pos, segment_id=seg1, vendor_id=v, status="allowed")

    resp = await client.get(f"/vendors/{v}/where-allowed")
    assert resp.status_code == 200
    standards = resp.json()["standards"]
    std = next(s for s in standards if s["building_type_id"] == bt)
    assert std["position_count"] == 1
    chips = {c["segment_name"]: c for c in std["positions"][0]["chips"]}
    assert chips["Класс-1"]["state"] == "allowed"
    assert chips["Класс-2"]["state"] == "excluded"
    assert chips["Класс-2"]["release_label"] == "ред. API"
