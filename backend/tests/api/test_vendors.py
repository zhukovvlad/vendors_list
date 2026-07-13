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


async def _aliases(db_conn, vendor_id: int) -> list[str]:
    return [
        r["alias"]
        for r in (
            await db_conn.execute(
                text("SELECT alias FROM vendor_alias WHERE vendor_id = :v ORDER BY alias"),
                {"v": vendor_id},
            )
        ).mappings()
    ]


async def _name(db_conn, vendor_id: int) -> str:
    return (
        await db_conn.execute(text("SELECT name FROM vendor WHERE id = :v"), {"v": vendor_id})
    ).scalar_one()


async def _note(db_conn, vendor_id: int) -> str | None:
    return (
        await db_conn.execute(text("SELECT note FROM vendor WHERE id = :v"), {"v": vendor_id})
    ).scalar_one()


async def test_patch_name_moves_old_to_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="Старое имя")
    resp = await client.patch(f"/vendors/{v}", json={"name": "Новое имя"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Новое имя"
    assert await _name(db_conn, v) == "Новое имя"
    assert "Старое имя" in await _aliases(db_conn, v)  # пр.1: старое имя → алиас


async def test_patch_name_round_trip_alias_state(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="A")
    await client.patch(f"/vendors/{v}", json={"name": "B"})
    await client.patch(f"/vendors/{v}", json={"name": "A"})
    # пр.1: конечное состояние — name=A, алиасы ровно {B} (мусор не накопился)
    assert await _name(db_conn, v) == "A"
    assert await _aliases(db_conn, v) == ["B"]


async def test_patch_name_duplicate_vendor_name_409(client, as_admin, db_conn) -> None:
    a = await f.make_vendor(db_conn, name="Alpha")
    await f.make_vendor(db_conn, name="Beta")
    resp = await client.patch(f"/vendors/{a}", json={"name": "Beta"})
    assert resp.status_code == 409


async def test_patch_name_clash_with_other_alias_409(client, as_admin, db_conn) -> None:
    owner = await f.make_vendor(db_conn, name="Owner")
    await f.make_alias(db_conn, vendor_id=owner, alias="ЗанятыйАлиас")
    v = await f.make_vendor(db_conn, name="Mover")
    resp = await client.patch(f"/vendors/{v}", json={"name": "ЗанятыйАлиас"})
    assert resp.status_code == 409  # пр.2: коллизия имени с чужим алиасом


async def test_patch_note_set_and_clear(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="note-vendor")
    await client.patch(f"/vendors/{v}", json={"note": "заметка"})
    assert await _note(db_conn, v) == "заметка"
    resp = await client.patch(f"/vendors/{v}", json={"note": ""})  # пр.3: "" → NULL
    assert resp.status_code == 200
    assert await _note(db_conn, v) is None


async def test_patch_note_absent_leaves_untouched(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="keep-note")
    await client.patch(f"/vendors/{v}", json={"note": "сохранить"})
    await client.patch(f"/vendors/{v}", json={"name": "keep-note-2"})  # note не в теле
    assert await _note(db_conn, v) == "сохранить"  # пр.3: поле не пришло → не трогаем


async def test_patch_blank_name_422(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="blank-name")
    resp = await client.patch(f"/vendors/{v}", json={"name": "   "})
    assert resp.status_code == 422


async def test_patch_missing_vendor_404(client, as_admin) -> None:
    resp = await client.patch("/vendors/999999", json={"name": "x"})
    assert resp.status_code == 404


async def test_patch_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="patch-viewer")
    resp = await client.patch(f"/vendors/{v}", json={"name": "nope"})
    assert resp.status_code == 403


async def test_where_allowed_segment_count(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-segcount")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-3", sort_order=3)
    cat = await f.make_category(db_conn, name="wa-sc-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-sc-pos")
    v = await f.make_vendor(db_conn, name="wa-sc-v")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed"
    )

    resp = await client.get(f"/vendors/{v}/where-allowed")
    assert resp.status_code == 200
    std = next(s for s in resp.json()["standards"] if s["building_type_id"] == bt)
    assert std["segment_count"] == 3  # знаменатель = ВСЕ сегменты типа
    assert len(std["positions"][0]["chips"]) == 1  # вендор только в одном


async def _live_cell_count(db_conn, vendor_id: int) -> int:
    return (
        await db_conn.execute(
            text(
                "SELECT count(*) FROM listing "
                "WHERE vendor_id = :v AND status = 'allowed' AND deleted_at IS NULL"
            ),
            {"v": vendor_id},
        )
    ).scalar_one()


async def test_add_listings_insert_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-ins")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    s2 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    cat = await f.make_category(db_conn, name="add-ins-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-ins-pos")
    v = await f.make_vendor(db_conn, name="add-ins-v")

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1, s2]}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 2
    # маркер открытого релиза создан
    assert (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one() == 1


async def test_add_listings_mixed_building_types_422(client, as_admin, db_conn) -> None:
    # Сегменты из РАЗНЫХ типов объекта → 422, без частичной записи (open-маркер
    # ставится один; смешанный запрос оставил бы второй тип без маркера).
    bt1 = await f.make_building_type(db_conn, code="add-mix1")
    bt2 = await f.make_building_type(db_conn, code="add-mix2")
    s1 = await f.make_segment(db_conn, building_type_id=bt1, name="Кл-1", sort_order=1)
    s2 = await f.make_segment(db_conn, building_type_id=bt2, name="Кл-2", sort_order=1)
    cat = await f.make_category(db_conn, name="add-mix-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-mix-pos")
    v = await f.make_vendor(db_conn, name="add-mix-v")

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1, s2]}
    )
    assert resp.status_code == 422
    # ни одной живой строки не записано, ни одного open-маркера не создано
    assert await _live_cell_count(db_conn, v) == 0
    for bt in (bt1, bt2):
        assert (
            await db_conn.execute(
                text(
                    "SELECT count(*) FROM release "
                    "WHERE building_type_id = :bt AND status = 'open'"
                ),
                {"bt": bt},
            )
        ).scalar_one() == 0


async def test_add_listings_undelete_branch_no_history(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-und")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="add-und-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-und-pos")
    v = await f.make_vendor(db_conn, name="add-und-v")
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed"
    )
    await db_conn.execute(
        text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid}
    )

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1]}
    )
    assert resp.status_code == 204
    # та же строка ожила — не наплодили дубль-историю
    total = (
        await db_conn.execute(
            text(
                "SELECT count(*) FROM listing "
                "WHERE position_id = :p AND segment_id = :s AND vendor_id = :v"
            ),
            {"p": pos, "s": s1, "v": v},
        )
    ).scalar_one()
    assert total == 1
    assert await _live_cell_count(db_conn, v) == 1


async def test_add_listings_meta_row_conflict_409(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-409")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="add-409-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-409-pos")
    v = await f.make_vendor(db_conn, name="add-409-v")
    # живая мета-строка (requirement) в ячейке → добавить вендора нельзя
    await f.make_listing(
        db_conn,
        position_id=pos,
        segment_id=s1,
        vendor_id=None,
        status="requirement",
        spec_text="Россия",
    )

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1]}
    )
    assert resp.status_code == 409


async def test_exclude_class_scale(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="exc-cls")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="exc-cls-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="exc-cls-pos")
    v = await f.make_vendor(db_conn, name="exc-cls-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "class", "position_id": pos, "segment_id": s1},
    )
    assert resp.status_code == 200
    assert resp.json() == {"excluded_positions": 1, "excluded_classes": 1}
    assert await _live_cell_count(db_conn, v) == 0


async def test_exclude_position_scale(client, as_admin, db_conn) -> None:
    """scope=position должен фильтровать классы ЧЕРЕЗ segment.building_type_id,
    а не по одной лишь position_id: bt2 делит ту же позицию с bt1, но его класс
    НЕ должен быть задет исключением, объявленным для bt1 (граница building_type)."""
    bt = await f.make_building_type(db_conn, code="exc-pos")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    s2 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    cat = await f.make_category(db_conn, name="exc-pos-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="exc-pos-pos")
    v = await f.make_vendor(db_conn, name="exc-pos-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos, segment_id=s2, vendor_id=v, status="allowed")

    # bt2 делит ТУ ЖЕ позицию (pos), тот же вендор — его класс должен пережить
    # исключение scope=position, объявленное для bt1.
    bt2 = await f.make_building_type(db_conn, code="exc-pos-bt2")
    s3 = await f.make_segment(db_conn, building_type_id=bt2, name="Кл-1-bt2", sort_order=1)
    await f.make_listing(db_conn, position_id=pos, segment_id=s3, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "position", "position_id": pos, "building_type_id": bt},
    )
    assert resp.status_code == 200
    # масштаб не изменился из-за bt2 — исключены ровно 2 класса bt1, не 3
    assert resp.json() == {"excluded_positions": 1, "excluded_classes": 2}
    # bt2-класс пережил исключение bt1: осталась ровно 1 живая ячейка (s3)
    assert await _live_cell_count(db_conn, v) == 1


async def test_exclude_standard_scale(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="exc-std")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="exc-std-cat")
    pos1 = await f.make_position(db_conn, category_id=cat, name="exc-std-p1")
    pos2 = await f.make_position(db_conn, category_id=cat, name="exc-std-p2")
    v = await f.make_vendor(db_conn, name="exc-std-v")
    await f.make_listing(db_conn, position_id=pos1, segment_id=s1, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos2, segment_id=s1, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "standard", "building_type_id": bt},
    )
    assert resp.status_code == 200
    assert resp.json() == {"excluded_positions": 2, "excluded_classes": 2}
    assert await _live_cell_count(db_conn, v) == 0


async def test_exclude_noop_returns_zeros_no_marker(client, as_admin, db_conn) -> None:
    """Нечего исключать (нет живых allowed-строк) → 200, нули, open-маркер НЕ создан.
    Прямая проверка семантики «маркер только при rowcount>0» (решение #2)."""
    bt = await f.make_building_type(db_conn, code="exc-noop")
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    v = await f.make_vendor(db_conn, name="exc-noop-v")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "standard", "building_type_id": bt},
    )
    assert resp.status_code == 200  # идемпотентно, НЕ 404
    assert resp.json() == {"excluded_positions": 0, "excluded_classes": 0}
    # rowcount==0 → ensure_open_release не вызван → фантомного черновика нет
    assert (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one() == 0


async def test_restore_undelete_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="res-und")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="res-und-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="res-und-pos")
    v = await f.make_vendor(db_conn, name="res-und-v")
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed"
    )
    await db_conn.execute(text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid})

    resp = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": pos, "segment_id": s1}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 1


async def test_restore_insert_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="res-ins")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="res-ins-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="res-ins-pos")
    v = await f.make_vendor(db_conn, name="res-ins-v")
    # никакой строки нет (excluded = released−live, живой строки в БД может не быть)

    resp = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": pos, "segment_id": s1}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 1


async def test_restore_meta_row_conflict_409(client, as_admin, db_conn) -> None:
    """restore разделяет _add_one_class с add — тот же P0001→409 путь на живой
    мета-строке в ячейке; фиксируем контракт явным тестом (зеркало
    test_add_listings_meta_row_conflict_409)."""
    bt = await f.make_building_type(db_conn, code="res-409")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="res-409-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="res-409-pos")
    v = await f.make_vendor(db_conn, name="res-409-v")
    # живая мета-строка (requirement) в ячейке → восстановить вендора нельзя
    await f.make_listing(
        db_conn,
        position_id=pos,
        segment_id=s1,
        vendor_id=None,
        status="requirement",
        spec_text="Россия",
    )

    resp = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": pos, "segment_id": s1}
    )
    assert resp.status_code == 409


async def test_patch_kind(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="kind-v", kind="manufacturer")
    resp = await client.patch(f"/vendors/{v}", json={"kind": "supplier"})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "supplier"


async def test_patch_kind_invalid_422(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="kind-bad-v")
    resp = await client.patch(f"/vendors/{v}", json={"kind": "producer"})
    assert resp.status_code == 422


async def test_patch_kind_explicit_null_422(client, as_admin, db_conn) -> None:
    # kind — NOT NULL: явный null отклоняется валидатором (422), а не доходит до
    # UPDATE ... SET kind = NULL (иначе 500). «Поле не пришло» этим не задето.
    v = await f.make_vendor(db_conn, name="kind-null-v", kind="supplier")
    resp = await client.patch(f"/vendors/{v}", json={"kind": None})
    assert resp.status_code == 422
    # значение не изменилось
    resp2 = await client.get(f"/vendors/{v}")
    assert resp2.json()["kind"] == "supplier"


async def test_listing_mutations_rbac_viewer_403(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="rbac-v")
    r1 = await client.post(f"/vendors/{v}/listings", json={"position_id": 1, "segment_ids": [1]})
    r2 = await client.post(
        f"/vendors/{v}/listings/exclude", json={"scope": "standard", "building_type_id": 1}
    )
    r3 = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": 1, "segment_id": 1}
    )
    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403
