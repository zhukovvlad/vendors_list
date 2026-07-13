"""ensure_open_release (ревизия 0006): единственный открытый маркер на тип объекта.

Обычный TDD: функция НОВАЯ, до наката 0006 на тест-ветку тест падает.
Настоящую параллельность в pytest не воспроизвести — проверяем идемпотентность
и ветку ON CONFLICT (повторный вызов переиспользует существующий id).
"""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _open_count(db_conn, bt: int) -> int:
    return (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one()


async def test_ensure_open_release_creates_when_absent(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="eor-create", name="ЖК-тест")
    rid = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    assert rid is not None
    assert await _open_count(db_conn, bt) == 1
    row = (
        await db_conn.execute(
            text("SELECT label, status FROM release WHERE id = :id"), {"id": rid}
        )
    ).mappings().one()
    assert row["status"] == "open"
    assert row["label"].strip() != ""  # NOT NULL, нейтральный непустой текст
    assert "рабочая версия" in row["label"]


async def test_ensure_open_release_idempotent_reuse(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="eor-reuse", name="Офис-тест")
    first = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    second = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    assert first == second  # ветка ON CONFLICT → переиспользован тот же маркер
    assert await _open_count(db_conn, bt) == 1  # второго открытого не появилось
