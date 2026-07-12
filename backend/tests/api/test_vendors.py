"""Карточка вендора: чтение шапки/дерева, мутации, RBAC."""

import pytest
from sqlalchemy import text

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


async def test_where_allowed_404(client, as_viewer) -> None:
    resp = await client.get("/vendors/999999/where-allowed")
    assert resp.status_code == 404


async def _agreement_log_count(db_conn, vendor_id: int) -> int:
    return (
        await db_conn.execute(
            text(
                "SELECT count(*) FROM agreement_change_log "
                "WHERE agreement_id IN (SELECT id FROM agreement WHERE vendor_id = :v)"
            ),
            {"v": vendor_id},
        )
    ).scalar_one()


async def _agreement_count(db_conn, vendor_id: int, status: str | None = None) -> int:
    sql = "SELECT count(*) FROM agreement WHERE vendor_id = :v"
    params = {"v": vendor_id}
    if status is not None:
        sql += " AND status = :s"
        params["s"] = status
    return (await db_conn.execute(text(sql), params)).scalar_one()


async def test_toggle_on_inserts_active(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-on")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    assert resp.json()["starred"] is True
    assert await _agreement_count(db_conn, v, "active") == 1


async def test_toggle_off_terminates_active(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-off")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["starred"] is False
    assert await _agreement_count(db_conn, v, "active") == 0
    assert await _agreement_count(db_conn, v, "terminated") == 1


async def test_toggle_on_after_off_creates_new_row(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-reon")
    await f.make_agreement(db_conn, vendor_id=v, status="terminated")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    # новая active-строка, старый terminated НЕ реанимирован
    assert await _agreement_count(db_conn, v) == 2
    assert await _agreement_count(db_conn, v, "active") == 1
    assert await _agreement_count(db_conn, v, "terminated") == 1


async def test_toggle_on_expired_not_resurrected(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-exp")
    await f.make_agreement(db_conn, vendor_id=v, status="expired")
    await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert await _agreement_count(db_conn, v, "expired") == 1  # осталась expired
    assert await _agreement_count(db_conn, v, "active") == 1    # добавлена новая


async def test_toggle_on_when_active_is_noop(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-noop")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    before = await _agreement_log_count(db_conn, v)
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    # no-op: ни новой строки, ни записи в аудит (UPDATE не выполняется)
    assert await _agreement_count(db_conn, v) == 1
    assert await _agreement_log_count(db_conn, v) == before


async def test_toggle_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-viewer")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 403


async def test_add_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-add")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "AlAdd-2"})
    assert resp.status_code == 201
    assert resp.json()["alias"] == "AlAdd-2"


async def test_add_alias_duplicate_409(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-dup")
    await f.make_alias(db_conn, vendor_id=v, alias="DUP-ALIAS")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "DUP-ALIAS"})
    assert resp.status_code == 409


async def test_add_alias_missing_vendor_404(client, as_admin) -> None:
    resp = await client.post("/vendors/999999/aliases", json={"alias": "x"})
    assert resp.status_code == 404


async def test_remove_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-del")
    aid = await f.make_alias(db_conn, vendor_id=v, alias="al-del-1")
    resp = await client.delete(f"/vendors/{v}/aliases/{aid}")
    assert resp.status_code == 204


async def test_remove_alias_missing_404(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-del-miss")
    resp = await client.delete(f"/vendors/{v}/aliases/999999")
    assert resp.status_code == 404


async def test_alias_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-viewer")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "nope"})
    assert resp.status_code == 403
