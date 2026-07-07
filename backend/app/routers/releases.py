"""Издания (редакции). Выгрузка — из неизменяемого снимка ``release_listing``.

Фиксация издания вызывает функцию БД ``freeze_release`` через пишущую
транзакцию с идентичностью (аудит подписывается логином админа).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import CurrentUser, require_admin, require_user
from ..db import read_conn, tx
from ..schemas import ReleaseListingRow

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("", dependencies=[Depends(require_user)])
async def list_releases(conn: AsyncConnection = Depends(read_conn)) -> list[dict[str, Any]]:
    rows = (
        await conn.execute(text("SELECT * FROM release ORDER BY created_at DESC, id DESC"))
    ).mappings()
    return [dict(r) for r in rows]


@router.get(
    "/{release_id}/listing",
    response_model=list[ReleaseListingRow],
    dependencies=[Depends(require_user)],
)
async def release_listing(
    release_id: int, conn: AsyncConnection = Depends(read_conn)
) -> list[ReleaseListingRow]:
    rows = (
        await conn.execute(
            text(
                "SELECT * FROM release_listing WHERE release_id = :rid "
                "ORDER BY category_path, position_name, segment_name, sort_order, id"
            ),
            {"rid": release_id},
        )
    ).mappings()
    return [ReleaseListingRow.model_validate(dict(r)) for r in rows]


@router.post("/{release_id}/freeze", status_code=status.HTTP_200_OK)
async def freeze_release(
    release_id: int,
    admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> dict[str, Any]:
    """Зафиксировать издание (снимок живого перечня). Только admin."""
    try:
        await conn.execute(
            text("SELECT freeze_release(:rid, :author)"),
            {"rid": release_id, "author": admin.username},
        )
    except DBAPIError as exc:
        # Ошибки инвариантов БД (релиз не найден / уже зафиксирован) -> 409
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc.orig)) from exc
    return {"release_id": release_id, "status": "published"}
