"""GET /dashboard — сводка начального экрана поверх вьюх dashboard_*.

Строго read-only. is_stale считается здесь по :stale_days из конфига (не в теле
вьюхи). merge_candidate_pairs — из прикладного детекта; его сбой деградирует в
null, а не в 500 на весь экран.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_user
from ..config import Settings, get_settings
from ..db import read_conn
from ..schemas import Dashboard, DashboardDraft, DashboardSummary
from ..services.dashboard import count_merge_candidates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard, dependencies=[Depends(require_user)])
async def get_dashboard(
    conn: AsyncConnection = Depends(read_conn),
    settings: Settings = Depends(get_settings),
) -> Dashboard:
    summary_row = (
        await conn.execute(text("SELECT * FROM dashboard_summary"))
    ).mappings().one()

    draft_rows = (
        await conn.execute(
            text(
                "SELECT release_id, building_type_name, label, "
                "last_touched_at, last_touched_by, "
                "(last_touched_at < now() - make_interval(days => :d)) AS is_stale "
                "FROM dashboard_open_drafts ORDER BY last_touched_at DESC"
            ),
            {"d": settings.dashboard_stale_days},
        )
    ).mappings().all()

    try:
        pairs = await count_merge_candidates(conn)
    except Exception:  # noqa: BLE001 — детект НЕ должен ронять экран
        logger.warning("merge-candidate detect raised; degrading to null", exc_info=True)
        pairs = None

    return Dashboard(
        summary=DashboardSummary(**dict(summary_row), merge_candidate_pairs=pairs),
        drafts=[DashboardDraft.model_validate(dict(r)) for r in draft_rows],
    )
