# Logging System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Внедрить централизованное логирование по образцу CIW — `setup_logging()` (консоль + ротируемые файлы) и ASGI `RequestIdMiddleware` с `request_id`-корреляцией.

**Architecture:** Два плоских модуля в `app/` (stdlib `logging`, zero-dependency): `logging_config.py` (root-логгер + contextvar + фильтр) и `middleware.py` (чистый ASGI, биндит `request_id`, отдаёт `X-Request-ID`, логирует строку запроса). Конфиг — из env (`os.getenv`), не из Settings. `setup_logging()` — первой строкой `create_app()` (не в lifespan: `app = create_app()` выполняется на импорте).

**Tech Stack:** Python 3.12, stdlib `logging`/`logging.handlers`, `contextvars`, Starlette ASGI, FastAPI, pytest (`asyncio_mode="auto"`), uv.

**Spec:** [docs/superpowers/specs/2026-07-09-logging-system-design.md](../specs/2026-07-09-logging-system-design.md)

## Global Constraints

- **stdlib-only** для логирования — новых зависимостей не добавлять.
- **Только `request_id`** — ни `task_id` (нет Celery), ни user-контекствара.
- **Конфиг из env:** `LOG_LEVEL` (INFO), `LOG_TO_FILE` (1), `LOG_DIR` (`backend/logs`). `os.getenv`, НЕ Settings. pydantic читает `.env` сам и НЕ наполняет `os.environ` — LOG_* задаются реальным env / just-рецептами.
- **Уровни — хендлерам, root=DEBUG** («пол»).
- **`parents[1]`** для дефолтного пути (файл в `app/`, не `app/core/`).
- **Формат:** `%(asctime)s | %(levelname)-7s | %(name)-25s | req=%(request_id)s | %(message)s` (без `task=`).
- **Плоское размещение:** `app/logging_config.py`, `app/middleware.py` (папок `core/`/`api/` нет).
- **Ветка:** `feat/logging-system`. Перед пушем — `just ci`. В `main` не коммитить.
- **asyncio_mode="auto"** — async-тесты без `@pytest.mark.asyncio`. Тесты логирования — НЕ `db`-маркер (чистые юниты).

---

### Task 1: Модуль `logging_config.py` + юнит-тесты

**Files:**
- Create: `backend/app/logging_config.py`
- Test: `backend/tests/test_logging_config.py`

**Interfaces:**
- Produces:
  - `setup_logging() -> None` — идемпотентная настройка root.
  - `_default_log_dir() -> Path` — чистый хелпер, `backend/logs`.
  - `bind_request_id(value: str | None) -> None`, `get_request_id() -> str | None`, `reset_correlation() -> None`.
  - `RequestIdFilter` (logging.Filter), contextvar `_request_id_var`, флаг `_configured`.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_logging_config.py`:

```python
"""Юнит-тесты централизованной настройки логирования (чистые, без БД)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_logging_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.logging_config'` (или ImportError).

- [ ] **Step 3: Реализовать модуль**

`backend/app/logging_config.py`:

```python
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
        record.request_id = _request_id_var.get() or "-"  # type: ignore[attr-defined]
        return True


def setup_logging() -> None:
    """Идемпотентно настраивает root-логгер: консоль + (опц.) ротируемые файлы."""
    global _configured
    if _configured:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
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
    logging.getLogger(__name__).info(
        "Логирование инициализировано (level=%s, to_file=%s, dir=%s)", level, to_file, log_dir
    )
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend; uv run pytest tests/test_logging_config.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Коммит**

```bash
git add backend/app/logging_config.py backend/tests/test_logging_config.py
git commit -m "feat(logging): setup_logging + request_id-корреляция (перенос паттерна CIW)"
```

---

### Task 2: ASGI `RequestIdMiddleware` + тесты

**Files:**
- Create: `backend/app/middleware.py`
- Test: `backend/tests/test_middleware.py`

**Interfaces:**
- Consumes: `bind_request_id`, `reset_correlation` из `app.logging_config` (Task 1).
- Produces: `RequestIdMiddleware` (ASGI-класс), `_sanitize(raw: str) -> str`, `_incoming_request_id(scope) -> str`. Логгер `app.request`.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_middleware.py`:

```python
"""Тесты ASGI RequestIdMiddleware: генерация/переиспользование/санитайз request_id
+ строка лога запроса. Своё минимальное Starlette-приложение, без БД."""

from __future__ import annotations

import logging

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.middleware import RequestIdMiddleware, _incoming_request_id, _sanitize


def _build_app() -> Starlette:
    async def ping(request):
        return PlainTextResponse("pong")

    app = Starlette(routes=[Route("/ping", ping)])
    app.add_middleware(RequestIdMiddleware)
    return app


def test_sanitize_strips_control_and_truncates():
    assert "\x00" not in _sanitize("a\x00b\x1f")
    assert _sanitize("a\x00b") == "ab"
    assert len(_sanitize("x" * 100)) == 64


def test_incoming_request_id_generates_when_absent():
    rid = _incoming_request_id({"headers": []})
    assert len(rid) == 8  # uuid4().hex[:8]


def test_incoming_request_id_reuses_header():
    scope = {"headers": [(b"x-request-id", b"abc123")]}
    assert _incoming_request_id(scope) == "abc123"


def test_incoming_request_id_regenerates_when_header_all_control():
    scope = {"headers": [(b"x-request-id", b"\x00\x01")]}
    assert len(_incoming_request_id(scope)) == 8  # пусто после санитайза → фоллбэк


async def test_response_carries_request_id_header():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/ping")
    assert r.status_code == 200
    assert len(r.headers["x-request-id"]) == 8


async def test_response_reuses_incoming_request_id():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/ping", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_request_line_is_logged(caplog):
    # app.request пропагирует до root; caplog вешает свой хендлер — свой в тесте не нужен.
    with caplog.at_level(logging.INFO, logger="app.request"):
        transport = ASGITransport(app=_build_app())
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.get("/ping")
    assert any("/ping" in rec.getMessage() for rec in caplog.records)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_middleware.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.middleware'`.

- [ ] **Step 3: Реализовать middleware**

`backend/app/middleware.py`:

```python
"""Чистый ASGI-middleware корреляции: request_id в contextvar + заголовок ответа + лог запроса.

BaseHTTPMiddleware не используем — у него проблемы с видимостью contextvar в
эндпоинте (разные контексты). Чистый ASGI ставит contextvar в той же корутине,
что зовёт downstream.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import bind_request_id, reset_correlation

logger = logging.getLogger("app.request")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(raw: str) -> str:
    """Чистит клиентский X-Request-ID: control-символы прочь, длина ≤ 64 (анти-log-injection)."""
    return _CONTROL.sub("", raw)[:64]


def _incoming_request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == b"x-request-id":
            rid = _sanitize(value.decode("latin-1"))
            if rid:  # непустой после вычистки — переиспользуем; иначе фоллбэк ниже
                return rid
            break
    return uuid4().hex[:8]


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        bind_request_id(request_id)
        start = time.monotonic()
        status = {"code": 500}  # 500 = ответ так и не начался (необработанный краш downstream)

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self._app(scope, receive, _send)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "%s %s → %s за %d мс",
                scope.get("method", "?"),
                scope.get("path", "?"),
                status["code"],
                duration_ms,
            )
            reset_correlation()
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend; uv run pytest tests/test_middleware.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Коммит**

```bash
git add backend/app/middleware.py backend/tests/test_middleware.py
git commit -m "feat(logging): ASGI RequestIdMiddleware (request_id + X-Request-ID + лог запроса)"
```

---

### Task 3: Проводка в приложение + сессионная изоляция файлов

**Files:**
- Modify: `backend/tests/conftest.py` (добавить `os.environ.setdefault` в начало, ДО импорта `app.main`)
- Modify: `backend/app/main.py` (setup_logging первой строкой create_app; middleware после CORS; убрать basicConfig/log_level)
- Modify: `backend/app/config.py:15` (удалить поле `log_level`)
- Modify: `backend/scripts/seed_vendors.py` (setup_logging в начале main)

**Interfaces:**
- Consumes: `setup_logging` (Task 1), `RequestIdMiddleware` (Task 2).

**Почему conftest первым:** `app = create_app()` в `app/main.py` выполняется на импорте модуля. `conftest.py` импортирует `app.main` (строка 24) при сборе тестов — раньше любой фикстуры. После этой задачи `create_app()` зовёт `setup_logging()`, и при дефолте `LOG_TO_FILE=1` создаст `backend/logs` во время тестов. Значит `LOG_TO_FILE=0` надо выставить в `os.environ` в самом верху `conftest.py`, ДО `from app.main import app`. `setdefault` уважает явное переопределение. Session-фикстура здесь опоздала бы (импорт уже случился).

- [ ] **Step 1: conftest — заглушить файлы для всей тест-сессии**

В `backend/tests/conftest.py` добавить в самое начало, СРАЗУ после docstring и `from __future__`, ДО остальных импортов (особенно `from app.main import app`):

```python
import os

# setup_logging() зовётся на импорте app.main (create_app). Гасим файловые
# хендлеры для всей тест-сессии, чтобы тесты не плодили backend/logs.
# ДО импорта app.* — иначе setup_logging уже отработает с дефолтом =1.
os.environ.setdefault("LOG_TO_FILE", "0")
```

Точное место: между строкой `from __future__ import annotations` (стр. 9) и первым блоком импортов (`from collections.abc ...`, стр. 11).

- [ ] **Step 2: main.py — setup_logging + middleware, убрать basicConfig**

В `backend/app/main.py`:

1. Импорты — заменить `import logging` на импорты новых модулей:

```python
from .config import get_settings
from .db import dispose_engine
from .logging_config import setup_logging
from .middleware import RequestIdMiddleware
from .routers import compliance, listings, meta, releases
```

2. В `lifespan` удалить строку `logging.basicConfig(level=settings.log_level)` (стр. 25). Итог:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.is_prod and settings.auth_dev_bypass:
        raise RuntimeError("AUTH_DEV_BYPASS must be false in production")
    yield
    await dispose_engine()
```

3. В `create_app` — `setup_logging()` первой строкой; `RequestIdMiddleware` ПОСЛЕ CORS (внешний слой):

```python
def create_app() -> FastAPI:
    setup_logging()  # первой строкой: create_app выполняется на импорте модуля
    settings = get_settings()
    app = FastAPI(
        title="Vendors API",
        version="0.1.0",
        summary="Учёт вендор-листов и соответствия проектов стандартам",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ПОСЛЕ CORS → RequestIdMiddleware становится ВНЕШНИМ (ставит request_id первым).
    app.add_middleware(RequestIdMiddleware)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (meta, listings, releases, compliance):
        app.include_router(module.router)

    return app
```

- [ ] **Step 3: config.py — удалить осиротевшее поле**

В `backend/app/config.py` удалить строку 15:

```python
    log_level: str = "INFO"
```

(остаётся `app_env: str = "dev"` и далее без изменений.)

- [ ] **Step 4: seed_vendors.py — логи в CLI**

В `backend/scripts/seed_vendors.py`:

1. Импорт: добавить рядом с `from app.seed.loader import run`:

```python
from app.logging_config import setup_logging
```

2. Первой строкой `main()` (стр. 32, до `argparse`):

```python
def main() -> int:
    setup_logging()
    ap = argparse.ArgumentParser(description="Сид вендор-листов из Excel в живые таблицы.")
```

- [ ] **Step 5: Прогнать весь backend — ничего не сломалось, файлы не появились**

Run: `cd backend; uv run pytest -q`
Expected: PASS (db-тесты скипаются без `DATABASE_URL_TEST`; логи-тесты зелёные).
Проверить, что каталог не создан:

Run: `cd backend; test -d logs && echo "ОШИБКА: logs создан" || echo "ok: logs нет"`
Expected: `ok: logs нет`

- [ ] **Step 6: Коммит**

```bash
git add backend/tests/conftest.py backend/app/main.py backend/app/config.py backend/scripts/seed_vendors.py
git commit -m "feat(logging): проводка setup_logging+middleware в приложение и сид; сессионный LOG_TO_FILE=0"
```

---

### Task 4: justfile, README, .env.example, .gitignore

**Files:**
- Modify: `justfile` (рецепты `dev-back`, `seed`, `test` — прокинуть LOG_* в окружение)
- Modify: `README.md` (правило env-only настроек)
- Modify: `backend/.env.example:21` (убрать LOG_LEVEL, заменить комментарием)
- Modify: `.gitignore` (добавить `backend/logs/`)
- Local (не коммитится): `backend/.env:20` — убрать `LOG_LEVEL=INFO`

- [ ] **Step 1: .gitignore — игнорировать логи**

В `.gitignore`, в блок `# --- Generated ---` добавить строку:

```
backend/logs/
```

- [ ] **Step 2: justfile — прокинуть LOG_* дефолты**

PowerShell-рецепты: каждая строка — отдельный вызов оболочки, env ставим на той же строке перед командой (`env_var_or_default` сам окружение дочернего процесса не наполняет — присваиваем `$env:` явно).

`dev-back` — LOG_LEVEL из env или INFO:

```
dev-back:
    cd {{backend}}; $env:LOG_LEVEL = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { 'INFO' }; uv run uvicorn app.main:app --reload --port 8000
```

`seed` — то же:

```
seed *args:
    cd {{backend}}; $env:LOG_LEVEL = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { 'INFO' }; uv run python -m scripts.seed_vendors {{args}}
```

`test` — заглушить файлы (belt-and-suspenders поверх conftest):

```
test:
    cd {{backend}}; $env:LOG_TO_FILE = '0'; uv run pytest
    cd {{frontend}}; npm run test
```

- [ ] **Step 3: .env.example — убрать LOG_LEVEL, оставить правило**

В `backend/.env.example` строку 21 (`LOG_LEVEL=INFO`) заменить на:

```
# LOG_LEVEL/LOG_TO_FILE/LOG_DIR — НЕ здесь: pydantic читает .env, но не наполняет
# os.environ, а логирование читает их через os.getenv. Задавать реальным env или
# just-рецептами (см. README, раздел «Логирование»).
```

- [ ] **Step 4: README — правило env-only настроек**

В `README.md` после раздела `## Быстрый старт` (перед `## Полезные команды`, ~стр. 53) добавить:

```markdown
## Логирование

Централизованная настройка — `app.logging_config.setup_logging()` (консоль +
ротируемые `backend/logs/app.log`, `errors.log`), корреляция запросов через
`X-Request-ID`.

**Правило env-only настроек.** `LOG_LEVEL`, `LOG_TO_FILE`, `LOG_DIR` читаются
через `os.getenv`, а НЕ через Settings. pydantic-settings читает `backend/.env`
самостоятельно и **не** наполняет `os.environ` — поэтому значения из `.env` для
`os.getenv` невидимы. Задавать их нужно реальным окружением или через
just-рецепты (`dev-back`/`seed` ставят `LOG_LEVEL=INFO` по умолчанию,
переопределяется реальным env). Разовый DEBUG: `$env:LOG_LEVEL='DEBUG'; just dev-back`.
Это правило общее для всех env-only настроек, не только логов.
```

- [ ] **Step 5: Локально убрать LOG_LEVEL из backend/.env (не коммитится — gitignored)**

В `backend/.env` строку 20 (`LOG_LEVEL=INFO`) удалить (файл в `.gitignore`, поэтому в коммит не попадёт — шаг только для чистоты локального окружения).

- [ ] **Step 6: Полный CI зелёный**

Run: `just ci`
Expected: types, lint (ruff + prettier --check), typecheck, test — всё PASS. `logs/` в рабочем дереве не появился.

- [ ] **Step 7: Коммит**

```bash
git add justfile README.md backend/.env.example .gitignore
git commit -m "chore(logging): LOG_* через env/just, README-правило env-only, backend/logs в .gitignore"
```

---

## Self-Review

**Spec coverage:**
- `setup_logging` (env-конфиг, хендлеры, уровни, UTF-8, глушилки, uvicorn-хендофф, sqlalchemy=WARNING) → Task 1. ✅
- `_default_log_dir` чистый хелпер, `parents[1]` → Task 1 (тест + реализация). ✅
- `RequestIdMiddleware` (санитайз, генерация, X-Request-ID, лог запроса) → Task 2. ✅
- Формат без `task=`, только `request_id` → Task 1 (формат + фильтр). ✅
- setup_logging первой строкой create_app, middleware после CORS, basicConfig прочь → Task 3. ✅
- `Settings.log_level` удалить → Task 3, Step 3. ✅
- seed CLI setup_logging → Task 3, Step 4. ✅
- Сессионный LOG_TO_FILE=0 (ДО импорта app.main) → Task 3, Step 1. ✅
- Изоляция глобального состояния в юнит-тестах (сохранить root, сбросить _configured, закрыть хендлеры) → Task 1, `clean_logging`. ✅
- justfile env_var_or_default, README-правило, .env.example, .gitignore backend/logs → Task 4. ✅
- Пре-флайт греп/`.gitignore` — выполнен на этапе брейншторма (хиты: `.env:20`, `.env.example:21`, `config.py:15`, `main.py:25`; `logs/` не игнорировался). ✅

**Placeholder scan:** плейсхолдеров нет — весь код и команды приведены дословно.

**Type consistency:** `setup_logging`, `_default_log_dir`, `bind_request_id`/`get_request_id`/`reset_correlation`, `RequestIdFilter`, `RequestIdMiddleware`, `_sanitize`, `_incoming_request_id` — имена совпадают между определением (Tasks 1–2) и потреблением (Tasks 2–3). Логгер `app.request` един в middleware и тесте.
