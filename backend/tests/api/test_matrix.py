"""GET /listings/matrix: контракт (обязательность building_type_id, форма ответа)."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_requires_building_type_id(client, as_viewer) -> None:
    resp = await client.get("/listings/matrix")
    assert resp.status_code == 422  # building_type_id обязателен


async def test_shape_keys(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    body = (await client.get("/listings/matrix", params={"building_type_id": bt})).json()
    assert set(body) == {"columns", "items", "total", "limit", "offset"}
    assert isinstance(body["columns"], list) and isinstance(body["items"], list)
