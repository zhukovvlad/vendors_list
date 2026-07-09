"""Централизованная настройка логирования: setup_logging() + request-корреляция.

Уровни задаём ХЕНДЛЕРАМ; root — DEBUG (пол), иначе дефолтный WARNING срежет
INFO/DEBUG ещё до хендлеров. LOG_LEVEL/LOG_TO_FILE/LOG_DIR читаем из env, НЕ из
Settings — логирование не должно зависеть от валидации DATABASE_URL/OIDC
(скрипты/сид настраивают логи до неё). pydantic читает .env сам и НЕ наполняет
os.environ — LOG_* задаём реальным окружением или just-рецептами, не в .env.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from pathlib import Path

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)-25s | req=%(request_id)s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_NOISY = ("httpx", "httpcore", "urllib3", "watchfiles")

_configured = False


def get_request_id() -> str | None:
    return _request_id_var.get()


def bind_request_id(value: str | None) -> None:
    _request_id_var.set(value)


def reset_correlation() -> None:
    _request_id_var.set(None)


def _default_log_dir() -> Path:
    """backend/logs. parents[1] — файл в app/, значит parents[1] = backend."""
    return Path(__file__).resolve().parents[1] / "logs"


class RequestIdFilter(logging.Filter):
    """Подмешивает request_id из contextvar в каждую запись; дефолт '-'."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        return True


def setup_logging() -> None:
    """Идемпотентно настраивает root-логгер: консоль + (опц.) ротируемые файлы."""
    global _configured
    if _configured:
        return

    # Невалидный LOG_LEVEL не роняет старт (setLevel кинул бы ValueError), но и не
    # глотается молча: откат на INFO + WARNING ниже, называющий плохое значение.
    raw_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = raw_level if raw_level in logging.getLevelNamesMapping() else "INFO"
    to_file = os.getenv("LOG_TO_FILE", "1") != "0"
    log_dir = Path(os.getenv("LOG_DIR", str(_default_log_dir())))

    # Кириллица в Windows-консоли (cp866 → UnicodeEncodeError). errors=replace — страховка.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    id_filter = RequestIdFilter()
    handlers: list[logging.Handler] = []

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)
    console.addFilter(id_filter)
    handlers.append(console)

    if to_file:
        os.makedirs(log_dir, exist_ok=True)  # ДО создания файловых хендлеров
        app_file = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        app_file.setFormatter(formatter)
        app_file.setLevel(logging.DEBUG)
        app_file.addFilter(id_filter)
        handlers.append(app_file)

        err_file = logging.handlers.RotatingFileHandler(
            log_dir / "errors.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        err_file.setFormatter(formatter)
        err_file.setLevel(logging.WARNING)
        err_file.addFilter(id_filter)
        handlers.append(err_file)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # пол = минимум по хендлерам; иначе WARNING срежет INFO/DEBUG
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    # app.log на DEBUG иначе зальёт каждый SQL с bind-параметрами. echo=True на
    # движке принудительно вернёт INFO поверх этого — явный опт-ин.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Хендофф uvicorn: записи идут через наш root (без своих хендлеров, без дублей).
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # access спамит INFO на каждый запрос — строка middleware информативнее (req= + мс).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _configured = True
    log = logging.getLogger(__name__)
    if level != raw_level:
        log.warning("Неизвестный LOG_LEVEL=%r — откат на INFO", raw_level)
    log.info(
        "Логирование инициализировано (level=%s, to_file=%s, dir=%s)", level, to_file, log_dir
    )
