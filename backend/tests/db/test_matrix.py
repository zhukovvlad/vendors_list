"""GET /listings/matrix поверх listing_live: server pivot, пагинация по позициям,
группировка колонок, звезда как есть, стык q×segment_id. Изоляция — фильтр по
свежесозданным данным (БД штатно заполнена сидом)."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_row_not_torn_and_star_as_is(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg_biz = await f.get_segment_id(db_conn, name="Бизнес")
    seg_eco = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="МатрицаТест-Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="МатрицаТест-Насосы")
    v = await f.make_vendor(db_conn, name="Mtx-Grundfos")
    await f.make_agreement(db_conn, vendor_id=v, status="active")  # звезда
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg_biz, vendor_id=v, status="allowed"
    )
    await f.make_listing(db_conn, position_id=pos, segment_id=seg_eco, vendor_id=None,
                         status="requirement", spec_text="Россия")

    resp = await client.get(
        "/listings/matrix", params={"building_type_id": bt, "q": "МатрицаТест-Насосы"}
    )
    assert resp.status_code == 200
    body = resp.json()
    row = next(r for r in body["items"] if r["position_id"] == pos)
    # Обе ячейки позиции на одной странице (строка не порвана):
    by_seg = {c["segment_id"]: c for c in row["cells"]}
    assert by_seg[seg_biz]["vendors"][0]["name"] == "Mtx-Grundfos"
    assert by_seg[seg_biz]["vendors"][0]["starred"] is True   # звезда из БД как есть
    assert by_seg[seg_eco]["vendors"] == [] and by_seg[seg_eco]["spec_text"] == "Россия"
    assert body["total"] >= 1 and body["limit"] == 50 and body["offset"] == 0


async def test_office_column_grouping(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="office")
    resp = await client.get("/listings/matrix", params={"building_type_id": bt})
    assert resp.status_code == 200
    cols = resp.json()["columns"]
    groups = {g["group"]["name"]: [s["name"] for s in g["segments"]] for g in cols if g["group"]}
    assert groups["Офисные здания"] == ["Prime", "Класс А", "Класс B"]
    assert groups["ТРЦ"] == ["ТРЦ"]


async def test_residential_columns_flat(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    cols = (await client.get("/listings/matrix", params={"building_type_id": bt})).json()["columns"]
    assert all(g["group"] is None for g in cols)  # жилые — без групп
    flat = [s["name"] for g in cols for s in g["segments"]]
    assert "Бизнес" in flat and len(flat) == 6


async def test_segment_id_narrows_columns(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cols = (await client.get("/listings/matrix",
            params={"building_type_id": bt, "segment_id": seg})).json()["columns"]
    seg_ids = [s["id"] for g in cols for s in g["segments"]]
    assert seg_ids == [seg]  # ровно одна колонка


async def test_q_with_segment_id_excludes_empty_in_class(client, as_viewer, db_conn) -> None:
    # Позиция матчит q по пути, но НЕ имеет ряда в суженном сегменте → отсутствует.
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg_biz = await f.get_segment_id(db_conn, name="Бизнес")
    seg_eco = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="УникПутьZZ")
    pos = await f.make_position(db_conn, category_id=cat, name="ПозицияZZ")
    v = await f.make_vendor(db_conn, name="Zz-Vendor")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg_biz, vendor_id=v, status="allowed"
    )

    # q по пути "УникПутьZZ", но сужаем на Эконом, где ряда нет → позиции нет.
    body = (await client.get("/listings/matrix",
            params={"building_type_id": bt, "segment_id": seg_eco, "q": "УникПутьZZ"})).json()
    assert all(r["position_id"] != pos for r in body["items"])
    # А без сужения (или на Бизнес) — позиция есть:
    body2 = (await client.get("/listings/matrix",
             params={"building_type_id": bt, "segment_id": seg_biz, "q": "УникПутьZZ"})).json()
    assert any(r["position_id"] == pos for r in body2["items"])
