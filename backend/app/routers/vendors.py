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
from ..schemas import VendorAlias, VendorCard, VendorRepresents

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
