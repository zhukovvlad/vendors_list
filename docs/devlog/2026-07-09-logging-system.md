# 2026-07-09 — Система логирования (setup_logging + request_id-middleware)

Ветка `feat/logging-system` → PR [#10](https://github.com/zhukovvlad/vendors_list/pull/10).
Реализовано по методике subagent-driven-development (план
[docs/superpowers/plans/2026-07-09-logging-system.md](../superpowers/plans/2026-07-09-logging-system.md),
спека
[docs/superpowers/specs/2026-07-09-logging-system-design.md](../superpowers/specs/2026-07-09-logging-system-design.md)):
Opus-оркестратор + двухстадийное ревью (spec + quality) на каждый дифф, исполнители —
Sonnet (задачи 1–3), Haiku (задача 4, доки/конфиг), финал — ревью всей ветки на Opus.

## Зачем

До этого логирование было единственной строкой `logging.basicConfig(level=settings.log_level)`
в lifespan — ни корреляции запросов, ни файлов, ни middleware. Цель — перенести обкатанный
паттерн соседнего проекта **CIW** (тот же стек: FastAPI + uv, stdlib `logging`, Windows):
единая настройка root-логгера (консоль + ротируемые файлы) и сквозной `request_id` на запрос.
С прицелом на будущую миграцию auth к CIW-подобной модели — один паттерн на два проекта.

## Что сделано (4 задачи, TDD)

- **[`app/logging_config.py`](../../backend/app/logging_config.py)** — `setup_logging()`
  (идемпотентно через модульный флаг `_configured`): консоль + `RotatingFileHandler`
  `app.log`@DEBUG / `errors.log`@WARNING (10 МБ × 5, UTF-8). Уровни навешиваются **хендлерам**,
  `root=DEBUG` («пол» — иначе дефолтный WARNING срезал бы INFO/DEBUG до хендлеров). Корреляция
  `request_id` через `ContextVar` + `RequestIdFilter` (формат
  `%(asctime)s | %(levelname)-7s | %(name)-25s | req=%(request_id)s | %(message)s`, дефолт `-`).
  Глушилки шумных логгеров → WARNING, `sqlalchemy.engine` → WARNING отдельно (иначе `app.log`
  зальёт SQL с bind-параметрами; `echo=True` — явный опт-ин поверх). Хендофф uvicorn: три
  логгера (`uvicorn`/`uvicorn.access`/`uvicorn.error`) отдают записи нашему root без своих
  хендлеров, `uvicorn.access` → WARNING (строка middleware информативнее). UTF-8-консоль под
  Windows через `sys.stdout.reconfigure(errors="replace")` в try/except.
- **[`app/middleware.py`](../../backend/app/middleware.py)** — **чистый ASGI**
  `RequestIdMiddleware` (не `BaseHTTPMiddleware`: contextvar должен ставиться в той же корутине,
  что зовёт downstream, иначе он не виден в эндпоинте). Берёт входящий `X-Request-ID`,
  санитайзит (control-символы прочь, ≤ 64 — анти-log-injection), переиспользует непустой либо
  генерит `uuid4().hex[:8]`; отдаёт `X-Request-ID` в ответе; в `finally` логирует строку запроса
  (`метод путь → статус за N мс`) и делает `reset_correlation()`. `status` дефолт 500 = ответ так
  и не начался (необработанный краш downstream).
- **Проводка** — `setup_logging()` **первой строкой `create_app()`** (не в lifespan: `app =
  create_app()` выполняется на импорте модуля, INFO при импорте иначе ушёл бы в
  `lastResort`/stderr с порогом WARNING и молча пропал). `RequestIdMiddleware` регистрируется
  **после** CORS → становится внешним слоем (ставит `request_id` первым, заголовок висит даже на
  CORS-preflight). Удалены `logging.basicConfig` и осиротевшее поле `Settings.log_level`.
  `setup_logging()` добавлен в `seed_vendors.py::main()`.
- **Env-only конфиг + доки** — `LOG_LEVEL`/`LOG_TO_FILE`/`LOG_DIR` читаются через `os.getenv`,
  **не** через Settings (логи поднимаются до валидации `DATABASE_URL`/OIDC; один источник уровня).
  Важный нюанс, вынесенный в README: pydantic читает `.env` сам, но **не** наполняет
  `os.environ`, поэтому `LOG_*` из `.env` для `os.getenv` невидимы — задаются реальным env или
  just-рецептами (`dev-back`/`seed` дефолтят `LOG_LEVEL=INFO`; `test` ставит `LOG_TO_FILE=0`).
  `.gitignore` → `backend/logs/`.

## Верификация

- **Юнит-тесты (чистые, без БД):** `test_logging_config.py` (идемпотентность, уровни хендлеров,
  `RequestIdFilter`, uvicorn-хендофф, `sqlalchemy.engine`, чистый `_default_log_dir`, откат
  невалидного `LOG_LEVEL`) + `test_middleware.py` (санитайз/генерация/переиспользование
  `X-Request-ID`, строка лога через `caplog`, реальный прогон через Starlette + httpx
  `ASGITransport`). Итого 8 + 7.
- **Изоляция файлов в тестах:** `setup_logging()` теперь зовётся на импорте `app.main`, поэтому
  **любой** api-тест создал бы `backend/logs` при дефолте `LOG_TO_FILE=1`. Гасим на всю сессию:
  `os.environ.setdefault("LOG_TO_FILE", "0")` в самом верху `conftest.py`, **до**
  `from app.main import app` (session-фикстура опоздала бы — импорт уже случился). Это делает
  последующие импорты «не в начале файла» → узаконено ruff `per-file-ignores` E402 на `conftest.py`.
- **`just ci` зелёный** локально и на PR #10 (backend pytest 98 passed, вкл. db-тесты на
  эфемерной ветке Neon; frontend vitest 5; ruff/prettier/mypy/tsc чисто). CodeRabbit — зелёный.

## Решения и нюансы

- **Только `request_id`** — без `task_id` (Celery/воркера нет) и **без** user-контекствара:
  CIW сам не биндит user в логи, личность живёт в аудите БД (`app.user` из `tx()`); user-бинд
  связал бы логи с auth-слоем, который планируется переписывать. Добавится одной строкой в новом
  auth, когда он устаканится.
- **Ловушка, вскрытая финальным ревью:** `just types` и **сам CI напрямую**
  (`ci.yml`: `uv run python -m scripts.export_openapi`) импортируют `app.main` → `create_app()` →
  `setup_logging()` с `LOG_TO_FILE` unset (=1) и плодили `backend/logs` при простом дампе схемы.
  Фикс — **script-level** (рецептный не покрыл бы прямой вызов CI): `export_openapi.py` ставит
  `os.environ.setdefault("LOG_TO_FILE", "0")` до импорта app (inline `# noqa: E402`).
- **Валидация `LOG_LEVEL`** (замечание CodeRabbit / финального ревью): невалидное значение
  (напр. `VERBOSE`) роняло старт через `ValueError` из `setLevel`. Выбран **откат на INFO +
  WARNING**, называющий плохое значение, а не тихий фоллбэк — тихий прятал бы опечатку оператора
  (форма silent failure для конфига наблюдаемости).
- **Плоское размещение** `app/logging_config.py` + `app/middleware.py` (конвенция проекта:
  `config.py`/`db.py`/`auth.py` в `app/`, папок `core/`/`api/` нет — в отличие от CIW).

## Что осталось / открытые хвосты

- **user-в-логах** — отложено до стабилизации нового auth (одна строка `bind`).
- **JSON-логи / внешний агрегатор** — не требуются на этом срезе.
- Мелкие отложенные (non-blocking, подтверждены ревью): `get_request_id()` пока без прямого
  потребителя (публичный API на будущее); `_sanitize` не срезает C1-контролы `0x80–0x9F`
  (CR/LF — основной вектор log-injection — покрыты); `RotatingFileHandler` — гипотетический
  `WinError 32` только при >1 воркере на хост в один файл (в dev один воркер — неактуально).
