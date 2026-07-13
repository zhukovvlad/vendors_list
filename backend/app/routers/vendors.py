"""Карточка вендора. Чтение — из готовых таблиц/функций БД; мутации — через tx.

Звезда (`starred`) приходит из функции БД `vendor_starred` (правило CLAUDE.md
№2 — не дублировать вычислимое в коде), роутер только собирает плоские строки
в объект ответа (презентация, не логика).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import CurrentUser, require_admin, require_user
from ..db import read_conn, tx
from ..schemas import (
    AgreementToggle,
    AliasCreate,
    ListingAdd,
    ListingExclude,
    ListingExcludeResult,
    ListingRestore,
    VendorAlias,
    VendorCard,
    VendorHeaderUpdate,
    VendorRepresents,
    WhereAllowed,
    WhereAllowedChip,
    WhereAllowedPosition,
    WhereAllowedStandard,
)

router = APIRouter(prefix="/vendors", tags=["vendors"])


async def _load_vendor_card(conn: AsyncConnection, vendor_id: int) -> VendorCard:
    """Собирает VendorCard из готовых объектов БД (starred — из vendor_starred).
    404, если вендора нет. Переиспользуется в GET и PATCH."""
    row = (
        await conn.execute(
            text("SELECT id, name, kind, represents_id, note FROM vendor WHERE id = :id"),
            {"id": vendor_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")

    starred = (
        await conn.execute(text("SELECT vendor_starred(:id)"), {"id": vendor_id})
    ).scalar_one()
    represented_count = (
        await conn.execute(
            text("SELECT count(*) FROM vendor WHERE represents_id = :id"), {"id": vendor_id}
        )
    ).scalar_one()

    represents = None
    if row["represents_id"] is not None:
        owner = (
            await conn.execute(
                text("SELECT id, name FROM vendor WHERE id = :id"), {"id": row["represents_id"]}
            )
        ).mappings().one()
        represents = VendorRepresents.model_validate(dict(owner))

    aliases = [
        VendorAlias.model_validate(dict(a))
        for a in (
            await conn.execute(
                text("SELECT id, alias FROM vendor_alias WHERE vendor_id = :id ORDER BY alias"),
                {"id": vendor_id},
            )
        ).mappings()
    ]

    return VendorCard(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        note=row["note"],
        starred=starred,
        represents=represents,
        represented_count=represented_count,
        aliases=aliases,
    )


@router.get("/{vendor_id}", response_model=VendorCard, dependencies=[Depends(require_user)])
async def get_vendor(vendor_id: int, conn: AsyncConnection = Depends(read_conn)) -> VendorCard:
    return await _load_vendor_card(conn, vendor_id)


@router.get(
    "/{vendor_id}/where-allowed",
    response_model=WhereAllowed,
    dependencies=[Depends(require_user)],
)
async def get_where_allowed(
    vendor_id: int, conn: AsyncConnection = Depends(read_conn)
) -> WhereAllowed:
    await _ensure_vendor(conn, vendor_id)
    rows = (
        await conn.execute(
            text("SELECT * FROM vendor_where_allowed(:v)"), {"v": vendor_id}
        )
    ).mappings().all()

    # Строки уже упорядочены (тип → позиция → класс) — группируем последовательно.
    standards: list[WhereAllowedStandard] = []
    for r in rows:
        if not standards or standards[-1].building_type_id != r["building_type_id"]:
            standards.append(
                WhereAllowedStandard(
                    building_type_id=r["building_type_id"],
                    building_type_name=r["building_type_name"],
                    position_count=0,
                    segment_count=0,
                    positions=[],
                )
            )
        std = standards[-1]
        if not std.positions or std.positions[-1].position_id != r["position_id"]:
            std.positions.append(
                WhereAllowedPosition(
                    position_id=r["position_id"],
                    position_name=r["position_name"],
                    chips=[],
                )
            )
            std.position_count += 1
        std.positions[-1].chips.append(
            WhereAllowedChip(
                segment_id=r["segment_id"],
                segment_name=r["segment_name"],
                state=r["state"],
                release_label=r["release_label"],
            )
        )

    if standards:
        counts = {
            row["building_type_id"]: row["n"]
            for row in (
                await conn.execute(
                    text(
                        "SELECT building_type_id, count(*) AS n "
                        "FROM segment GROUP BY building_type_id"
                    )
                )
            ).mappings()
        }
        for s in standards:
            s.segment_count = counts.get(s.building_type_id, 0)

    return WhereAllowed(standards=standards)


async def _ensure_vendor(conn: AsyncConnection, vendor_id: int) -> None:
    exists = (
        await conn.execute(text("SELECT 1 FROM vendor WHERE id = :id"), {"id": vendor_id})
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")


def _is_cell_chk(exc: DBAPIError) -> bool:
    """listing_cell_chk поднимает RAISE EXCEPTION (SQLSTATE P0001), не нарушение
    ограничения — это НЕ IntegrityError. Распознаём по sqlstate оригинала asyncpg."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == "P0001"


async def _segment_building_type(conn: AsyncConnection, segment_id: int) -> int:
    bt = (
        await conn.execute(
            text("SELECT building_type_id FROM segment WHERE id = :s"), {"s": segment_id}
        )
    ).scalar_one_or_none()
    if bt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Класс не найден")
    return int(bt)


async def _add_one_class(
    conn: AsyncConnection, vendor_id: int, position_id: int, segment_id: int
) -> bool:
    """Один класс: если уже жив — no-op (idempotent), возвращает False; иначе
    un-delete последней soft-deleted строки (чистим и deleted_by, чтобы ожившая
    строка не унесла устаревшего удалившего), иначе INSERT allowed — возвращает True
    (реальное изменение → вызывающий создаст open-маркер). Мета-строка в ячейке → 409."""
    live = (
        await conn.execute(
            text(
                "SELECT 1 FROM listing WHERE position_id = :p AND segment_id = :s "
                "AND vendor_id = :v AND deleted_at IS NULL"
            ),
            {"p": position_id, "s": segment_id, "v": vendor_id},
        )
    ).scalar_one_or_none()
    if live is not None:
        return False  # уже живой — no-op, маркер релиза не нужен
    try:
        res = await conn.execute(
            text(
                "UPDATE listing SET deleted_at = NULL, deleted_by = NULL WHERE id = ("
                "  SELECT id FROM listing WHERE position_id = :p AND segment_id = :s "
                "  AND vendor_id = :v AND deleted_at IS NOT NULL ORDER BY id DESC LIMIT 1)"
            ),
            {"p": position_id, "s": segment_id, "v": vendor_id},
        )
        if res.rowcount == 0:
            await conn.execute(
                text(
                    "INSERT INTO listing (position_id, segment_id, vendor_id, status) "
                    "VALUES (:p, :s, :v, 'allowed')"
                ),
                {"p": position_id, "s": segment_id, "v": vendor_id},
            )
        return True  # ожил (un-delete) ЛИБО вставлен — реальное изменение
    except DBAPIError as exc:
        if _is_cell_chk(exc):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Ячейка содержит требование/прочерк — сначала уберите мета-строку",
            ) from exc
        raise


@router.put("/{vendor_id}/agreement")
async def toggle_agreement(
    vendor_id: int,
    body: AgreementToggle,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> dict[str, bool]:
    """Тумблер соглашения (O1). Асимметрично, инвариант «одна активная строка»:
    вкл на уже активном — no-op (UPDATE не выполняем, чтобы не засорять аудит);
    иначе INSERT новой active (историю expired/terminated НЕ реанимируем).
    Выкл — терминируем активную. Аудит пишет триггер (changed_by = app.user)."""
    await _ensure_vendor(conn, vendor_id)
    if body.active:
        has_active = (
            await conn.execute(
                text("SELECT 1 FROM agreement WHERE vendor_id = :id AND status = 'active'"),
                {"id": vendor_id},
            )
        ).scalar_one_or_none()
        if has_active is None:
            await conn.execute(
                text("INSERT INTO agreement (vendor_id, status) VALUES (:id, 'active')"),
                {"id": vendor_id},
            )
    else:
        await conn.execute(
            text(
                "UPDATE agreement SET status = 'terminated' "
                "WHERE vendor_id = :id AND status = 'active'"
            ),
            {"id": vendor_id},
        )
    starred = (
        await conn.execute(text("SELECT vendor_starred(:id)"), {"id": vendor_id})
    ).scalar_one()
    return {"starred": starred}


@router.post(
    "/{vendor_id}/aliases",
    response_model=VendorAlias,
    status_code=status.HTTP_201_CREATED,
)
async def add_alias(
    vendor_id: int,
    body: AliasCreate,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> VendorAlias:
    await _ensure_vendor(conn, vendor_id)
    try:
        row = (
            await conn.execute(
                text(
                    "INSERT INTO vendor_alias (vendor_id, alias) "
                    "VALUES (:v, :a) RETURNING id, alias"
                ),
                {"v": vendor_id, "a": body.alias},
            )
        ).mappings().one()
    except IntegrityError as exc:
        # alias UNIQUE глобально → нарушение уникальности = 409
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой вариант написания уже занят") from exc
    return VendorAlias.model_validate(dict(row))


@router.patch("/{vendor_id}", response_model=VendorCard)
async def update_vendor_header(
    vendor_id: int,
    body: VendorHeaderUpdate,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> VendorCard:
    """Инлайн-правка шапки (имя и/или примечание, partial).

    Смена имени нормализует справочник: старое написание уходит в алиасы (пр.1,
    ON CONFLICT — идемпотентно для A→B→A). Коллизия нового имени с чужим именем
    (UNIQUE → IntegrityError) или чужим алиасом (пр.2, явная проверка) → 409.
    note: "" → NULL (пр.3); поле не в теле → не трогаем.
    """
    row = (
        await conn.execute(text("SELECT name FROM vendor WHERE id = :id"), {"id": vendor_id})
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")
    data = body.model_dump(exclude_unset=True)

    if "name" in data:
        new_name = data["name"]  # уже стрипнуто валидатором
        old_name = row["name"]
        if new_name != old_name:
            clash = (
                await conn.execute(
                    text("SELECT 1 FROM vendor_alias WHERE alias = :n AND vendor_id <> :id"),
                    {"n": new_name, "id": vendor_id},
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Имя уже занято")
            # снять дубль «новое имя == собственный алиас»
            await conn.execute(
                text("DELETE FROM vendor_alias WHERE vendor_id = :id AND alias = :n"),
                {"id": vendor_id, "n": new_name},
            )
            try:
                await conn.execute(
                    text("UPDATE vendor SET name = :n WHERE id = :id"),
                    {"n": new_name, "id": vendor_id},
                )
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "Имя уже занято") from exc
            # старое имя → алиас (идемпотентно)
            await conn.execute(
                text(
                    "INSERT INTO vendor_alias (vendor_id, alias) VALUES (:id, :old) "
                    "ON CONFLICT (alias) DO NOTHING"
                ),
                {"id": vendor_id, "old": old_name},
            )

    if "note" in data:
        raw = data["note"]
        note = raw.strip() if raw else None
        note = note or None
        await conn.execute(
            text("UPDATE vendor SET note = :note WHERE id = :id"),
            {"note": note, "id": vendor_id},
        )

    if "kind" in data:
        await conn.execute(
            text("UPDATE vendor SET kind = :k WHERE id = :id"),
            {"k": data["kind"], "id": vendor_id},
        )

    return await _load_vendor_card(conn, vendor_id)


@router.delete("/{vendor_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_alias(
    vendor_id: int,
    alias_id: int,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    res = await conn.execute(
        text("DELETE FROM vendor_alias WHERE id = :a AND vendor_id = :v"),
        {"a": alias_id, "v": vendor_id},
    )
    if res.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вариант написания не найден")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{vendor_id}/listings", status_code=status.HTTP_204_NO_CONTENT)
async def add_listings(
    vendor_id: int,
    body: ListingAdd,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    """Добавить вендора в позицию по классам. Общий для «+ класс»/«+ позиция»/«+ стандарт».
    Порядок блокировок listing → release ЕДИНЫЙ во всех мутациях (без дедлока при
    конкурентной правке одного типа): сперва пишем в listing, ensure_open_release —
    ПОСЛЕ и только если хоть один класс реально ожил (no-op не плодит фантомный
    черновик на дашборде, O2)."""
    await _ensure_vendor(conn, vendor_id)
    bt = await _segment_building_type(conn, body.segment_ids[0])
    changed = False
    for seg in body.segment_ids:
        if await _add_one_class(conn, vendor_id, body.position_id, seg):
            changed = True
    if changed:
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{vendor_id}/listings/exclude", response_model=ListingExcludeResult)
async def exclude_listings(
    vendor_id: int,
    body: ListingExclude,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> ListingExcludeResult:
    """Soft-delete вендора по scope (class/position/standard); deleted_by/аудит
    проставят триггеры. Порядок listing → release (как в add/restore): soft-delete
    СНАЧАЛА, ensure_open_release — ПОСЛЕ и только если реально исключили строки
    (rowcount>0; no-op не создаёт фантомный черновик, O2). Возвращает ФАКТИЧЕСКИЙ
    масштаб (для тоста/сверки; клиентский предрасчёт — только для мгновенного диалога)."""
    await _ensure_vendor(conn, vendor_id)
    bt: int
    if body.scope == "class":
        assert body.segment_id is not None  # гарантировано валидатором
        bt = await _segment_building_type(conn, body.segment_id)
    else:
        raw_bt = body.building_type_id
        assert raw_bt is not None  # гарантировано валидатором
        bt = raw_bt

    if body.scope == "class":
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND position_id = :p AND segment_id = :s "
            "AND deleted_at IS NULL RETURNING position_id"
        )
        params: dict[str, object] = {"v": vendor_id, "p": body.position_id, "s": body.segment_id}
    elif body.scope == "position":
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND position_id = :p AND deleted_at IS NULL "
            "AND segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
            "RETURNING position_id"
        )
        params = {"v": vendor_id, "p": body.position_id, "bt": bt}
    else:  # standard
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND deleted_at IS NULL "
            "AND segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
            "RETURNING position_id"
        )
        params = {"v": vendor_id, "bt": bt}

    pos_ids = (await conn.execute(text(sql), params)).scalars().all()
    if pos_ids:  # rowcount>0 → реальное изменение → создаём/переиспользуем open-маркер
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return ListingExcludeResult(
        excluded_classes=len(pos_ids),
        excluded_positions=len(set(pos_ids)),
    )


@router.post("/{vendor_id}/listings/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_listing(
    vendor_id: int,
    body: ListingRestore,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    """«Вернуть» один класс: un-delete-first-else-INSERT (O1). Порядок listing →
    release (как в add/exclude): сперва оживляем класс, ensure_open_release — ПОСЛЕ и
    только если реально изменили (уже-живой класс = no-op). Конфликт с мета-строкой → 409."""
    await _ensure_vendor(conn, vendor_id)
    bt = await _segment_building_type(conn, body.segment_id)
    if await _add_one_class(conn, vendor_id, body.position_id, body.segment_id):
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
