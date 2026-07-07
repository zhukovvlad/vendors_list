"""Модуль соответствия: проекты, выбор вендоров, светофор, сводка.

Чтение статусов — из вьюх ``compliance.project_position_status`` и
``compliance.project_summary`` (расчёт светофора живёт в БД). Запись выбора —
через пишущую транзакцию с идентичностью (аудит выбора append-only в БД).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_admin, require_user
from ..db import read_conn, tx
from ..schemas import (
    PositionStatus,
    Project,
    ProjectCreate,
    ProjectSummary,
    Selection,
    SelectionCreate,
)

router = APIRouter(prefix="/projects", tags=["compliance"])


@router.get("", response_model=list[Project], dependencies=[Depends(require_user)])
async def list_projects(conn: AsyncConnection = Depends(read_conn)) -> list[Project]:
    rows = (await conn.execute(text("SELECT * FROM compliance.project ORDER BY code"))).mappings()
    return [Project.model_validate(dict(r)) for r in rows]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    _: object = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Project:
    try:
        row = (
            (
                await conn.execute(
                    text(
                        "INSERT INTO compliance.project (code, name, segment_id, release_id, note) "
                        "VALUES (:code, :name, :segment_id, :release_id, :note) RETURNING *"
                    ),
                    body.model_dump(),
                )
            )
            .mappings()
            .one()
        )
    except DBAPIError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc.orig)) from exc
    return Project.model_validate(dict(row))


@router.get(
    "/{project_id}/positions",
    response_model=list[PositionStatus],
    dependencies=[Depends(require_user)],
)
async def project_positions(
    project_id: int, conn: AsyncConnection = Depends(read_conn)
) -> list[PositionStatus]:
    rows = (
        await conn.execute(
            text(
                "SELECT * FROM compliance.project_position_status "
                "WHERE project_id = :pid ORDER BY category_path, position_name"
            ),
            {"pid": project_id},
        )
    ).mappings()
    return [PositionStatus.model_validate(dict(r)) for r in rows]


@router.get(
    "/{project_id}/summary",
    response_model=ProjectSummary,
    dependencies=[Depends(require_user)],
)
async def project_summary(
    project_id: int, conn: AsyncConnection = Depends(read_conn)
) -> ProjectSummary:
    row = (
        (
            await conn.execute(
                text("SELECT * FROM compliance.project_summary WHERE project_id = :pid"),
                {"pid": project_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found or has no positions")
    return ProjectSummary.model_validate(dict(row))


@router.post(
    "/{project_id}/selections",
    response_model=Selection,
    status_code=status.HTTP_201_CREATED,
)
async def add_selection(
    project_id: int,
    body: SelectionCreate,
    _: object = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Selection:
    try:
        row = (
            (
                await conn.execute(
                    text(
                        "INSERT INTO compliance.project_selection "
                        "(project_id, position_id, vendor_id, rationale, source_ref) "
                        "VALUES (:project_id, :position_id, :vendor_id, :rationale, :source_ref) "
                        "RETURNING *"
                    ),
                    {"project_id": project_id, **body.model_dump()},
                )
            )
            .mappings()
            .one()
        )
    except DBAPIError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc.orig)) from exc
    return Selection.model_validate(dict(row))


@router.delete("/{project_id}/selections/{selection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_selection(
    project_id: int,
    selection_id: int,
    _: object = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> None:
    """Мягкое удаление выбора (deleted_at проставит триггер-штамп БД)."""
    result = await conn.execute(
        text(
            "UPDATE compliance.project_selection SET deleted_at = now() "
            "WHERE id = :sid AND project_id = :pid AND deleted_at IS NULL"
        ),
        {"sid": selection_id, "pid": project_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Selection not found")
