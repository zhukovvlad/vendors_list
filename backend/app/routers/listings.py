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
from ..schemas import (
    ListingRow,
    Matrix,
    MatrixCell,
    MatrixColumnGroup,
    MatrixRow,
    Page,
    SegmentGroupRef,
    SegmentRef,
)

router = APIRouter(prefix="/listings", tags=["listings"], dependencies=[Depends(require_user)])


def _group_columns(col_rows: list[dict[str, Any]]) -> list[MatrixColumnGroup]:
    """Свернуть упорядоченные строки сегментов в группы (consecutive by group_id).
    group_id NULL → одна группа с group=None (жилые/социальные)."""
    columns: list[MatrixColumnGroup] = []
    for r in col_rows:
        seg = SegmentRef(id=r["segment_id"], name=r["segment_name"], sort_order=r["seg_sort"])
        gid = r["group_id"]
        last_gid = columns[-1].group.id if (columns and columns[-1].group) else None
        if columns and last_gid == gid:
            columns[-1].segments.append(seg)
        else:
            grp = SegmentGroupRef(id=gid, name=r["group_name"]) if gid is not None else None
            columns.append(MatrixColumnGroup(group=grp, segments=[seg]))
    return columns


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


@router.get("/matrix", response_model=Matrix)
async def listing_matrix(
    building_type_id: int,
    segment_id: int | None = None,
    q: str | None = Query(None, description="Поиск по позиции/вендору/разделу"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: AsyncConnection = Depends(read_conn),
) -> Matrix:
    seg_f = "AND ll.segment_id = :seg" if segment_id is not None else ""
    # Пустая строка q — falsy, трактуется как «без фильтра» (согласовано с фронтом:
    # `q: search.q || undefined`).
    q_f = (
        "AND (ll.position_name ILIKE :q OR ll.vendor_name ILIKE :q OR ll.category_path ILIKE :q)"
        if q
        else ""
    )
    params: dict[str, Any] = {"bt": building_type_id}
    if segment_id is not None:
        params["seg"] = segment_id
    if q:
        params["q"] = f"%{q}%"

    total = (
        await conn.execute(
            text(
                "SELECT count(*) FROM (SELECT DISTINCT ll.position_id FROM listing_live ll "
                "WHERE ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
                f"{seg_f} {q_f}) t"
            ),
            params,
        )
    ).scalar_one()

    page = (
        await conn.execute(
            text(
                f"""
                WITH pos_page AS (
                    SELECT DISTINCT ll.position_id
                    FROM listing_live ll
                    WHERE ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt)
                      {seg_f} {q_f}
                ),
                cats AS (
                    SELECT d.category_id,
                           category_sort_path(d.category_id) AS csp,
                           category_path(d.category_id)      AS cpath
                    FROM (SELECT DISTINCT p.category_id
                          FROM pos_page pp JOIN position p ON p.id = pp.position_id) d
                )
                SELECT p.id AS position_id, p.name AS position_name, c.cpath AS category_path
                FROM pos_page pp
                JOIN position p ON p.id = pp.position_id
                JOIN cats c     ON c.category_id = p.category_id
                ORDER BY c.csp, p.sort_order, p.id
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )
    ).mappings().all()

    position_ids = [r["position_id"] for r in page]
    cells_by_pos: dict[int, dict[int, dict[str, Any]]] = {}
    if position_ids:
        cell_params: dict[str, Any] = {"bt": building_type_id, "pos_ids": position_ids}
        if segment_id is not None:
            cell_params["seg"] = segment_id
        cell_rows = (
            await conn.execute(
                text(
                    f"""
                    SELECT ll.position_id, ll.segment_id, ll.vendor_id, ll.vendor_name,
                           ll.vendor_starred, ll.ujin_integration, ll.spec_text, ll.note
                    FROM listing_live ll
                    WHERE ll.position_id = ANY(:pos_ids)
                      AND ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt)
                      {seg_f}
                    ORDER BY ll.position_id, ll.segment_id, ll.sort_order, ll.id
                    """
                ),
                cell_params,
            )
        ).mappings().all()
        for cr in cell_rows:
            seg_map = cells_by_pos.setdefault(cr["position_id"], {})
            cell = seg_map.setdefault(
                cr["segment_id"],
                {"segment_id": cr["segment_id"], "vendors": [], "spec_text": None, "note": None},
            )
            if cr["vendor_id"] is not None:
                cell["vendors"].append(
                    {
                        "vendor_id": cr["vendor_id"],
                        "name": cr["vendor_name"],
                        "starred": cr["vendor_starred"],
                        "ujin_integration": cr["ujin_integration"],
                        "note": cr["note"],
                    }
                )
            else:
                cell["spec_text"] = cr["spec_text"]
                cell["note"] = cr["note"]

    items = [
        MatrixRow(
            position_id=r["position_id"],
            position_name=r["position_name"],
            category_path=r["category_path"],
            cells=[MatrixCell(**c) for c in cells_by_pos.get(r["position_id"], {}).values()],
        )
        for r in page
    ]

    col_params: dict[str, Any] = {"bt": building_type_id}
    col_seg_f = ""
    if segment_id is not None:
        col_params["seg"] = segment_id
        col_seg_f = "AND s.id = :seg"
    col_rows = (
        await conn.execute(
            text(
                f"""
                SELECT s.id AS segment_id, s.name AS segment_name, s.sort_order AS seg_sort,
                       sg.id AS group_id, sg.name AS group_name
                FROM segment s
                LEFT JOIN segment_group sg ON sg.id = s.group_id
                WHERE s.building_type_id = :bt {col_seg_f}
                ORDER BY COALESCE(sg.sort_order, -1), sg.id, s.sort_order, s.id
                """
            ),
            col_params,
        )
    ).mappings().all()

    return Matrix(
        columns=_group_columns([dict(r) for r in col_rows]),
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
