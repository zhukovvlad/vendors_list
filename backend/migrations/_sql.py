"""Хелпер для накатывания .sql-файлов из ``migrations/sql/``.

Alembic уже оборачивает миграцию в транзакцию, поэтому внешние ``BEGIN;`` /
``COMMIT;`` из скрипта снимаем (иначе COMMIT закрыл бы транзакцию Alembic
раньше времени). Выполняем сырым драйвером (``exec_driver_sql``), чтобы
SQLAlchemy не трактовал ``:=`` в plpgsql как bind-параметры.

psycopg3 всё равно сканирует ``%`` как маркер плейсхолдера (даже без
параметров), а в SQL есть литеральные ``%`` в ``RAISE EXCEPTION '... %'``.
Поэтому удваиваем ``%`` -> ``%%`` — psycopg вернёт их в одинарные перед
отправкой на сервер.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

_SQL_DIR = Path(__file__).parent / "sql"


def run_sql_file(name: str) -> None:
    raw = (_SQL_DIR / name).read_text(encoding="utf-8")
    # снять внешние BEGIN;/COMMIT; (в любом регистре, с пробелами)
    body = re.sub(r"^\s*BEGIN\s*;", "", raw, count=1, flags=re.IGNORECASE)
    body = re.sub(r"COMMIT\s*;\s*$", "", body, count=1, flags=re.IGNORECASE)
    # экранировать литеральные % (см. docstring)
    body = body.replace("%", "%%")
    op.get_bind().exec_driver_sql(body)
