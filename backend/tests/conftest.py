"""Фикстуры pytest для бэкенд-тестов.

db-тесты (маркер `db`) идут против тестовой ветки Neon (DATABASE_URL_TEST).
Если URL не задан — db-тесты пропускаются, чтобы локальный `just ci` без
тест-базы оставался зелёным. URL читаем через Settings (pydantic видит и .env,
и env-переменные CI), а не через os.getenv.
"""

from __future__ import annotations

import pytest

from app.config import get_settings

TEST_DB_URL = get_settings().database_url_test


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if TEST_DB_URL:
        return
    skip_db = pytest.mark.skip(
        reason="DATABASE_URL_TEST не задан — интеграционные db-тесты пропущены"
    )
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
