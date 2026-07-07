"""Живой перечень — матрица позиций × классов. Источник: вьюха ``listing_live``.

Серверная пагинация/фильтрация под TanStack Table. Расчёт звезды/статусов —
в БД (``vendor_starred`` и т.п.), здесь только выборка.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_user
from ..db import read_conn
from ..schemas import ListingRow, Page

router = APIRouter(prefix="/listings", tags=["listings"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[ListingRow])
async def list_listings(
    segment_id: int | None = None,
    position_id: int | None = None,
    q: str | None = Query(None, description="Поиск по позиции/вендору/разделу"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn: AsyncConnection = Depends(read_conn),
) -> Page[ListingRow]:
    where: list[str] = []
    params: dict[str, Any] = {}
    if segment_id is not None:
        where.append("segment_id = :segment_id")
        params["segment_id"] = segment_id
    if position_id is not None:
        where.append("position_id = :position_id")
        params["position_id"] = position_id
    if q:
        where.append("(position_name ILIKE :q OR vendor_name ILIKE :q OR category_path ILIKE :q)")
        params["q"] = f"%{q}%"
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = (
        await conn.execute(text(f"SELECT count(*) FROM listing_live{clause}"), params)
    ).scalar_one()

    rows = (
        await conn.execute(
            text(
                f"SELECT * FROM listing_live{clause} "
                "ORDER BY category_path, position_name, segment_name, sort_order, id "
                "LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": limit, "offset": offset},
        )
    ).mappings()

    return Page(
        items=[ListingRow.model_validate(dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
