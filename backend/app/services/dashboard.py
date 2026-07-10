"""Дашборд: прикидочный детект похожих вендоров (гигиена справочника).

Нормализация/схлопывание брендов живёт в прикладном слое (не в БД). Кандидат-пара =
коллизия нормализованного имени между разными бренд-ключами. Триграммы — отложены.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# Убираем только ХВОСТОВОЙ маркер «(Native)» (в конце имени) — не любые скобки и не
# тот же маркер в середине. Скобки с брендом-владельцем («ИСТРАТЕХ (Grundfos)»)
# разрешаются через represents_id в данных, а не нормализацией имени; срезать все
# скобки нельзя — «Насос (300Вт)» и «(500Вт)» схлопнулись бы в ложный дубль. Якорь
# `\s*$` держит норму верной интенту: детект консервативный, пропуск лучше шума.
_TAIL = re.compile(r"\((?:native|нативный)\)\s*$", re.IGNORECASE)
_NONALNUM = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


def normalize_vendor_name(name: str) -> str:
    """lower + убрать общий хвост «(Native)» + схлопнуть пунктуацию/пробелы.

    НЕ трогает скобки с брендом-владельцем — это забота represents_id, не регэкспа."""
    s = _TAIL.sub(" ", name).lower()
    s = _NONALNUM.sub(" ", s)
    return " ".join(s.split())


async def count_merge_candidates(
    conn: AsyncConnection, *, timeout_ms: int = 1500
) -> int | None:
    """Число кандидат-пар (коллизия нормы между разными бренд-ключами).

    Устойчив к таймауту: SET LOCAL statement_timeout + перехват DBAPIError → None
    (медленный детект не должен ронять весь дашборд).

    SET LOCAL действует ТОЛЬКО внутри транзакции. read_conn в SQLAlchemy 2.0 (без
    AUTOCOMMIT) транзакционен, и к вызову коннект уже в неявной транзакции запроса
    (сводка/черновики прочитаны раньше) — таймаут применяется к SELECT ниже и
    сбрасывается при закрытии соединения (без утечки в пул). Если транзакции всё же
    нет (изменится порядок вызовов) — открываем и откатываем свою (детект read-only),
    чтобы гарантия таймаута не зависела от того, «кто открыл транзакцию раньше»."""
    own_txn = not conn.in_transaction()
    if own_txn:
        await conn.begin()
    try:
        await conn.execute(
            text("SELECT set_config('statement_timeout', :ms, true)"),
            {"ms": str(timeout_ms)},
        )
        rows = (
            await conn.execute(
                text("SELECT coalesce(represents_id, id) AS brand_id, name FROM vendor")
            )
        ).mappings().all()
    except DBAPIError:
        logger.warning("merge-candidate detect failed/timed out", exc_info=True)
        return None
    finally:
        if own_txn and conn.in_transaction():
            await conn.rollback()  # закрыть СВОЮ транзакцию → сбросить statement_timeout

    by_norm: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        by_norm[normalize_vendor_name(r["name"])].add(r["brand_id"])

    pairs = 0
    for brand_ids in by_norm.values():
        n = len(brand_ids)
        if n >= 2:
            pairs += n * (n - 1) // 2  # число пар среди схлопнувшихся брендов
    return pairs
