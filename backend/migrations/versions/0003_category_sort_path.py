"""Ревизия №3: функция сортировочного пути раздела (презентация, read-only).

category_sort_path(category_id) -> int[] — пары [sort_order, id] на уровень предка
(root→leaf). Массивное сравнение даёт детерминированный preorder даже при дублях
sort_order. Порядок отображения матрицы (spec §Выборка), инвариант не трогаем.

Revision ID: 0003_category_sort_path
Revises: 0002_compliance
"""

from __future__ import annotations

from alembic import op

revision = "0003_category_sort_path"
down_revision = "0002_compliance"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION category_sort_path(p_id int) RETURNS int[]
  LANGUAGE sql STABLE AS
$$
    WITH RECURSIVE up AS (
        SELECT id, parent_id, sort_order, 1 AS lvl FROM category WHERE id = p_id
        UNION ALL
        SELECT c.id, c.parent_id, c.sort_order, up.lvl + 1
        FROM category c JOIN up ON c.id = up.parent_id
    )
    SELECT array_agg(v ORDER BY lvl DESC, ord)
    FROM up
    CROSS JOIN LATERAL (VALUES (0, sort_order), (1, id)) AS pair(ord, v);
$$;
"""

_DOWN = "DROP FUNCTION IF EXISTS category_sort_path(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
