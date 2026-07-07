"""Справочники: типы объектов и классы (для фильтров/колонок матрицы)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import CurrentUser, require_user
from ..db import read_conn
from ..schemas import BuildingType, Segment

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(require_user)])


@router.get("/building-types", response_model=list[BuildingType])
async def building_types(conn: AsyncConnection = Depends(read_conn)) -> list[BuildingType]:
    rows = (
        await conn.execute(text("SELECT * FROM building_type ORDER BY sort_order, id"))
    ).mappings()
    return [BuildingType.model_validate(dict(r)) for r in rows]


@router.get("/segments", response_model=list[Segment])
async def segments(
    building_type_id: int | None = None,
    conn: AsyncConnection = Depends(read_conn),
    _: CurrentUser = Depends(require_user),
) -> list[Segment]:
    sql = "SELECT * FROM segment"
    params: dict[str, Any] = {}
    if building_type_id is not None:
        sql += " WHERE building_type_id = :bt"
        params["bt"] = building_type_id
    sql += " ORDER BY sort_order, id"
    rows = (await conn.execute(text(sql), params)).mappings()
    return [Segment.model_validate(dict(r)) for r in rows]
