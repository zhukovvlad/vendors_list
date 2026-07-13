"""Справочники: типы объектов и классы (для фильтров/колонок матрицы)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import CurrentUser, require_user
from ..db import read_conn
from ..schemas import BuildingType, MetaPosition, Segment

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


@router.get("/positions", response_model=list[MetaPosition])
async def positions(
    building_type_id: int,
    q: str | None = None,
    conn: AsyncConnection = Depends(read_conn),
) -> list[MetaPosition]:
    """Позиции, реально присутствующие в живом перечне типа объекта (для комбобокса
    «+ стандарт»). Тип достижим только через segment.building_type_id. q — поиск по
    имени/пути раздела. Лимит 50 (комбобокс с сужением по вводу)."""
    params: dict[str, Any] = {"bt": building_type_id}
    q_f = ""
    if q:
        q_f = "AND (p.name ILIKE :q OR category_path(p.category_id) ILIKE :q)"
        params["q"] = f"%{q}%"
    rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT p.id, p.name, category_path(p.category_id) AS category_path "
                "FROM position p "
                "JOIN listing l ON l.position_id = p.id AND l.deleted_at IS NULL "
                "JOIN segment s ON s.id = l.segment_id "
                f"WHERE s.building_type_id = :bt {q_f} "
                "ORDER BY p.name LIMIT 50"
            ),
            params,
        )
    ).mappings()
    return [MetaPosition.model_validate(dict(r)) for r in rows]
