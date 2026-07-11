"""Карточка вендора. Чтение — из готовых таблиц/функций БД; мутации — через tx.

Звезда (`starred`) приходит из функции БД `vendor_starred` (правило CLAUDE.md
№2 — не дублировать вычислимое в коде), роутер только собирает плоские строки
в объект ответа (презентация, не логика).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import CurrentUser, require_admin, require_user
from ..db import read_conn, tx
from ..schemas import (
    AgreementToggle,
    AliasCreate,
    VendorAlias,
    VendorCard,
    VendorRepresents,
    WhereAllowed,
    WhereAllowedChip,
    WhereAllowedPosition,
    WhereAllowedStandard,
)

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("/{vendor_id}", response_model=VendorCard, dependencies=[Depends(require_user)])
async def get_vendor(vendor_id: int, conn: AsyncConnection = Depends(read_conn)) -> VendorCard:
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


@router.get(
    "/{vendor_id}/where-allowed",
    response_model=WhereAllowed,
    dependencies=[Depends(require_user)],
)
async def get_where_allowed(
    vendor_id: int, conn: AsyncConnection = Depends(read_conn)
) -> WhereAllowed:
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

    return WhereAllowed(standards=standards)


async def _ensure_vendor(conn: AsyncConnection, vendor_id: int) -> None:
    exists = (
        await conn.execute(text("SELECT 1 FROM vendor WHERE id = :id"), {"id": vendor_id})
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")


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
    except DBAPIError as exc:
        # alias UNIQUE глобально → нарушение уникальности = 409
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой вариант написания уже занят") from exc
    return VendorAlias.model_validate(dict(row))


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
