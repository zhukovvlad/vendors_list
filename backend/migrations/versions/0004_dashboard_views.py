"""Ревизия №4: вьюхи дашборда «Обзор» (презентация, read-only).

dashboard_summary   — одна строка скалярных агрегатов (позиции в действующих
                      релизах, счётчики изданий, вендоры по бренд-ключу).
dashboard_open_drafts — открытые черновики с последней правкой (last_touched).
Инвариантов не добавляет. is_stale здесь НЕ считается — порог задаётся в запросе.

Revision ID: 0004_dashboard_views
Revises: 0003_category_sort_path
"""

from __future__ import annotations

from alembic import op

revision = "0004_dashboard_views"
down_revision = "0003_category_sort_path"
branch_labels = None
depends_on = None

_UP = """
CREATE VIEW dashboard_summary AS
WITH current_release AS (
    SELECT DISTINCT ON (building_type_id) id
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC
),
brands AS (
    SELECT DISTINCT coalesce(represents_id, id) AS brand_id FROM vendor
)
SELECT
    (SELECT count(DISTINCT rl.position_id)
       FROM release_listing rl
       JOIN current_release cr ON cr.id = rl.release_id
      WHERE rl.position_id IS NOT NULL)                        AS positions_active,
    (SELECT count(*) FROM release WHERE status = 'published')  AS releases_published,
    (SELECT count(*) FROM release WHERE status = 'open')       AS drafts_open,
    (SELECT count(*) FROM brands)                              AS vendors_total,
    (SELECT count(*) FROM brands WHERE vendor_starred(brand_id)) AS vendors_with_agreement;

CREATE VIEW dashboard_open_drafts AS
SELECT
    r.id                                    AS release_id,
    r.building_type_id,
    bt.name                                 AS building_type_name,
    r.label,
    coalesce(la.last_at, r.created_at)      AS last_touched_at,
    coalesce(la.last_by, r.author)          AS last_touched_by
FROM release r
JOIN building_type bt ON bt.id = r.building_type_id
LEFT JOIN LATERAL (
    SELECT max(l.updated_at) AS last_at,
           (array_agg(l.updated_by ORDER BY l.updated_at DESC))[1] AS last_by
    FROM listing l
    JOIN segment s ON s.id = l.segment_id
    WHERE s.building_type_id = r.building_type_id
      AND l.deleted_at IS NULL
) la ON true
WHERE r.status = 'open';
"""

_DOWN = """
DROP VIEW IF EXISTS dashboard_open_drafts;
DROP VIEW IF EXISTS dashboard_summary;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
