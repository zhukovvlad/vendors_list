"""Карточка вендора. Чтение — из готовых таблиц/функций БД; мутации — через tx.

Звезда (`starred`) приходит из функции БД `vendor_starred` (правило CLAUDE.md
№2 — не дублировать вычислимое в коде), роутер только собирает плоские строки
в объект ответа (презентация, не логика).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_user
from ..db import read_conn
from ..schemas import (
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
