"""Ревизия №6: ensure_open_release(building_type_id) — маркер открытого релиза.

Автосоздание «черновика» = обеспечение ЕДИНСТВЕННОГО open-маркера на тип объекта
(симметрия с freeze_release; инвариант в БД — CLAUDE.md #6). Гонка снимается
ограничением uq_release_one_open (0001), не сервисным локом: параллельные вызовы
конфликтуют по частичному уникальному индексу, проигравший переиспользует чужой id.

label — НЕЙТРАЛЬНЫЙ и не ложь: freeze_release НЕ перезаписывает label (0001:396-400),
значит любой авто-label доедет до published-релиза как есть. «<тип> — рабочая версия»
не утверждает ничего ложного; человек уточнит его при публикации (экран изданий, §5).

Revision ID: 0006_ensure_open_release
Revises: 0005_vendor_where_allowed
"""

from __future__ import annotations

from alembic import op

revision = "0006_ensure_open_release"
down_revision = "0005_vendor_where_allowed"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION ensure_open_release(p_bt int) RETURNS int LANGUAGE plpgsql AS
$fn$
DECLARE v_id int;
BEGIN
    INSERT INTO release (building_type_id, label, status)
    VALUES (p_bt,
            (SELECT name || ' — рабочая версия' FROM building_type WHERE id = p_bt),
            'open')
    ON CONFLICT (building_type_id) WHERE status = 'open' DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN            -- открытый маркер уже был (повтор/гонка)
        SELECT id INTO v_id FROM release
        WHERE building_type_id = p_bt AND status = 'open';
    END IF;
    RETURN v_id;
END;
$fn$;
"""

_DOWN = "DROP FUNCTION IF EXISTS ensure_open_release(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
