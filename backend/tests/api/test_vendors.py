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
