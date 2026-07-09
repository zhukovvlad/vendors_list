"""Юнит-тесты централизованной настройки логирования (чистые, без БД)."""

from __future__ import annotations

import logging
import logging.handlers

import pytest

from app import logging_config
from app.logging_config import (
    RequestIdFilter,
    _default_log_dir,
    bind_request_id,
    reset_correlation,
    setup_logging,
)


@pytest.fixture
def clean_logging(monkeypatch):
    """Изолирует глобальное состояние: сохраняет/восстанавливает root, сбрасывает
    _configured, глушит файлы (LOG_TO_FILE=0). Закрывает новые хендлеры на выходе,
    иначе открытый файловый хендлер сломает cleanup tmp_path на Windows."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    monkeypatch.setattr(logging_config, "_configured", False)
    monkeypatch.setenv("LOG_TO_FILE", "0")
    yield
    for h in [h for h in root.handlers if h not in saved_handlers]:
        h.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_default_log_dir_points_to_backend_logs():
    # Чистый хелпер: путь без вызова setup_logging и без создания файлов.
    d = _default_log_dir()
    assert d.name == "logs"
    assert d.parent.name == "backend"


def test_setup_logging_is_idempotent(clean_logging):
    setup_logging()
    count = len(logging.getLogger().handlers)
    setup_logging()  # второй вызов — no-op
    assert logging.getLogger().handlers.__len__() == count
    assert logging_config._configured is True


def test_console_handler_level_from_env(clean_logging, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging()
    console = logging.getLogger().handlers[0]
    assert console.level == logging.WARNING
    assert logging.getLogger().level == logging.DEBUG  # root = пол


def test_file_handlers_levels(clean_logging, monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_TO_FILE", "1")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    setup_logging()
    files = [
        h for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    levels = sorted(h.level for h in files)
    assert levels == [logging.DEBUG, logging.WARNING]
    assert (tmp_path / "app.log").exists()
    assert (tmp_path / "errors.log").exists()


def test_request_id_filter_default_and_bound(clean_logging):
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", None, None)
    f = RequestIdFilter()
    reset_correlation()
    f.filter(rec)
    assert rec.request_id == "-"
    bind_request_id("deadbeef")
    f.filter(rec)
    assert rec.request_id == "deadbeef"
    reset_correlation()


def test_uvicorn_access_muted_and_propagates(clean_logging):
    setup_logging()
    acc = logging.getLogger("uvicorn.access")
    assert acc.level == logging.WARNING
    assert acc.propagate is True
    assert acc.handlers == []


def test_sqlalchemy_engine_muted(clean_logging):
    setup_logging()
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
