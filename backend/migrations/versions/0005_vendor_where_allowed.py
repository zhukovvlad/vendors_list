"""Ревизия №5: функция vendor_where_allowed (обратный индекс «Где разрешён»).

Правило исключения (граница легитимности — релиз): вендор показывается по классу
как allowed, если жива строка listing со status='allowed'; как excluded — если он
был в снимке последнего published-релиза этого типа объекта, но живой строки нет.
Черновичные опечатки (не в релизе, добавлен и удалён) и «нигде не было» — не в
выборке. brand-key НЕ разворачиваем (фильтр строго по vendor_id).

Revision ID: 0005_vendor_where_allowed
Revises: 0004_dashboard_views
"""

from __future__ import annotations

from alembic import op

revision = "0005_vendor_where_allowed"
down_revision = "0004_dashboard_views"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION vendor_where_allowed(p_vendor_id int)
RETURNS TABLE (
    building_type_id   int,
    building_type_name text,
    position_id        int,
    position_name      text,
    segment_id         int,
    segment_name       text,
    state              text,
    release_label      text
) LANGUAGE sql STABLE AS
$fn$
WITH current_release AS (          -- последний published-релиз на каждый тип
    SELECT DISTINCT ON (building_type_id) id, building_type_id, label
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC
),
released AS (                      -- вендор в снимке этого релиза (allowed)
    SELECT DISTINCT cr.building_type_id, rl.position_id, rl.segment_id, cr.label
    FROM current_release cr
    JOIN release_listing rl ON rl.release_id = cr.id
    WHERE rl.vendor_id = p_vendor_id AND rl.status = 'allowed'
      AND rl.position_id IS NOT NULL AND rl.segment_id IS NOT NULL
),
live AS (                          -- вендор жив сейчас (allowed)
    SELECT seg.building_type_id, l.position_id, l.segment_id
    FROM listing l
    JOIN segment seg ON seg.id = l.segment_id
    WHERE l.vendor_id = p_vendor_id AND l.status = 'allowed'
      AND l.deleted_at IS NULL
),
keys AS (
    SELECT building_type_id, position_id, segment_id FROM live
    UNION
    SELECT building_type_id, position_id, segment_id FROM released
)
SELECT bt.id, bt.name, pos.id, pos.name, seg.id, seg.name,
       CASE WHEN lv.position_id IS NOT NULL THEN 'allowed' ELSE 'excluded' END,
       CASE WHEN lv.position_id IS NULL THEN rl.label ELSE NULL END
FROM keys k
JOIN building_type bt ON bt.id  = k.building_type_id
JOIN position      pos ON pos.id = k.position_id
JOIN segment       seg ON seg.id = k.segment_id
LEFT JOIN live     lv ON (lv.building_type_id, lv.position_id, lv.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
LEFT JOIN released rl ON (rl.building_type_id, rl.position_id, rl.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
ORDER BY bt.sort_order,
         category_sort_path(pos.category_id), pos.sort_order, pos.name,
         seg.sort_order, seg.name;
$fn$;
"""

_DOWN = "DROP FUNCTION IF EXISTS vendor_where_allowed(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
