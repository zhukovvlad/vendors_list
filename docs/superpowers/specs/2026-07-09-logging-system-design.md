# Дизайн: система логирования (перенос паттерна CIW)

**Дата:** 2026-07-09
**Статус:** утверждён к реализации
**Ветка:** `feat/logging-system`

## Цель

Внедрить централизованное логирование по образцу соседнего проекта **CIW**:
единая настройка root-логгера (консоль + ротируемые файлы) и сквозная
корреляция запросов через `request_id`. Тот же стек (FastAPI + uv, stdlib
`logging`, Windows), тот же паттерн в двух проектах — с прицелом на будущую
миграцию auth к CIW-подобной модели.

## Контекст

**Что есть в CIW** (образец):
- `app/core/logging_config.py` (125 строк) — `setup_logging()`, contextvar
  `request_id`+`task_id`, `RequestIdFilter`, глушилки шумных логгеров,
  UTF-8-консоль, хендофф uvicorn.
- `app/api/middleware.py` (70 строк) — чистый ASGI `RequestIdMiddleware`.

**Что у нас сейчас:**
- [main.py:25](../../../backend/app/main.py) — только `logging.basicConfig(level=settings.log_level)`.
- Ни корреляции, ни файлов, ни middleware.
- Есть [db.py](../../../backend/app/db.py) `tx()`, ставящий `app.user` → аудит в БД
  (`current_app_user()`) — «кто» уже пишется в базу.
- Celery/воркера **нет** — вся `task_id`-часть CIW неприменима.

## Решения (зафиксированы в брейншторме)

| # | Решение | Обоснование |
|---|---------|-------------|
| Объём | Полный аналог CIW: `setup_logging` + ASGI `RequestIdMiddleware` | тот же стек, stdlib-only |
| Корреляция | **Только `request_id`**, без `task_id` (нет Celery) и **без user-контекствара** | CIW сам не биндит user в логи; личность живёт в аудите БД (`app.user`); user-бинд связал бы логи с auth-слоем, который планируется переписывать |
| Источник конфига | **env** (`os.getenv`), не Settings | логи поднимаются до валидации `DATABASE_URL`; консистентно с CIW; один источник уровня логов |
| `Settings.log_level` | **удалить** | используется только в `main.py:25`, которую заменяем; иначе два конкурирующих источника |
| LOG_* в окружении | just-таски (`env_var_or_default`) + README-правило | pydantic читает `.env` сам и **не** наполняет `os.environ`; `os.getenv(LOG_*)` из `.env` невидим |
| `sqlalchemy.engine` | **WARNING** | app.log на DEBUG иначе зальёт SQL с bind-параметрами в файл; `echo=True` — явный опт-ин поверх WARNING |
| Размещение | плоское: `app/logging_config.py` + `app/middleware.py` | конвенция проекта (`config.py`/`db.py`/`auth.py` в `app/`, папок `core/`/`api/` нет) |

## Компоненты

### `backend/app/logging_config.py`

Перенос CIW-файла с правками. Публичный интерфейс:

- `setup_logging() -> None` — идемпотентно (модульный флаг `_configured`).
  Читает из env: `LOG_LEVEL` (дефолт `INFO`), `LOG_TO_FILE` (дефолт `1`),
  `LOG_DIR` (дефолт `parents[1]/"logs"` = `backend/logs`).
  **`parents[1]`, не `parents[2]`** — файл лежит в `app/`, а не `app/core/`.
- contextvar `_request_id_var: ContextVar[str | None]` + `RequestIdFilter`
  (подмешивает `record.request_id`, дефолт `-`).
- хелперы: `bind_request_id(value)`, `get_request_id()`, `reset_correlation()`.
  **Без** `task_id`: нет `_task_id_var`, нет `bind_task_id`, нет `task=` в формате.
- Формат:
  `%(asctime)s | %(levelname)-7s | %(name)-25s | req=%(request_id)s | %(message)s`
- Хендлеры (уровни навешиваются **хендлерам**, root=DEBUG «пол»):
  - console → `stdout`, level=`LOG_LEVEL`, фильтр.
  - при `LOG_TO_FILE`: `app.log` (DEBUG) + `errors.log` (WARNING),
    `RotatingFileHandler` 10 МБ × 5, `encoding="utf-8"`, фильтр.
    `os.makedirs(log_dir, exist_ok=True)` **до** создания файловых хендлеров.
- `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` в try/except
  (AttributeError, ValueError) — кириллица в Windows-консоли.
- Глушилки: `_NOISY = ("httpx", "httpcore", "urllib3", "watchfiles")` → WARNING.
  (`botocore`/`s3transfer` убраны — S3 нет; celery-блок убран.)
  `sqlalchemy.engine` → WARNING отдельно.
- Хендофф uvicorn: для **всех трёх** имён `("uvicorn", "uvicorn.access",
  "uvicorn.error")` — `handlers.clear()` + `propagate=True` (чтобы записи шли
  через наш root с `req=`-форматом, без дублей своим хендлером).
  **Дополнительно** только на `uvicorn.access` — `setLevel(WARNING)` (INFO-доступ
  глушим; строка middleware информативнее — `req=` + длительность). Уровень
  навешивается отдельно от цикла хендоффа.

### `backend/app/middleware.py`

Перенос CIW-файла **как есть, минус `task_id`** — правок по существу нет:

- `RequestIdMiddleware` — чистый ASGI (не `BaseHTTPMiddleware`: contextvar
  должен ставиться в той же корутине, что зовёт downstream).
- `_incoming_request_id(scope)`: берёт `X-Request-ID`, санитайзит
  (`_sanitize`: control-символы прочь, ≤ 64 — анти-log-injection),
  переиспользует непустой; иначе `uuid4().hex[:8]`.
- `bind_request_id` на входе; `X-Request-ID` в заголовок ответа; в `finally`
  `logger.info("%s %s → %s за %d мс", method, path, status, duration_ms)` и
  `reset_correlation()`. Логгер `app.request`.
- Регистрация в `create_app` **после** CORS → RequestIdMiddleware внешний
  (ставит `request_id` первым).

## Проводка

- **[main.py](../../../backend/app/main.py):**
  `setup_logging()` **первой строкой `create_app()`** (не в lifespan: `app =
  create_app()` выполняется на импорте модуля; INFO при импорте иначе уйдёт в
  `lastResort`/stderr с порогом WARNING и молча пропадёт). `logging.basicConfig`
  из lifespan удалить. `app.add_middleware(RequestIdMiddleware)` после CORS.
- **[config.py](../../../backend/app/config.py):** удалить поле `log_level`.
- **[scripts/seed_vendors.py](../../../backend/scripts/seed_vendors.py):**
  `setup_logging()` в начале `main()` (до разбора аргументов; print-отчёт
  dry-run с логами не конфликтует).
- **justfile:** рецепты `dev-back`/`seed` прокидывают дефолты через
  `env_var_or_default` (`LOG_LEVEL`=INFO и т.д.), переопределяемые реальным env.
  *Имплементационная деталь:* переменную надо именно `export`/прокинуть в
  команду — `env_var_or_default` сам окружение дочернего процесса не наполняет.
- **README:** блок-правило (жёсткая формулировка): «pydantic читает `.env` сам
  и **не** наполняет `os.environ`; всё, что читается через `os.getenv` (LOG_*),
  в `.env` не работает — задавать через реальный env или just-рецепты». Правило
  общее для всех env-only настроек, не только логов.
- **`.env.example`:** строку `LOG_LEVEL=INFO` (строка 21) заменить на
  комментарий «настраивается через env / just, не через .env» — первая
  иллюстрация README-правила. То же вычистить в `.env` (строка 20, локально).
- **`.gitignore`:** добавить `backend/logs/` (сейчас не игнорируется; при
  `LOG_TO_FILE=1` первый `just dev-back`/сид создаст `backend/logs/app.log`).

## Обработка ошибок

- `os.makedirs(exist_ok=True)` до файловых хендлеров.
- `reconfigure` в try/except (AttributeError, ValueError).
- Идемпотентность через `_configured` — повторный вызов no-op.
- Middleware: `status` дефолт 500 (ответ не начался = необработанный краш
  downstream); `reset_correlation()` в `finally`.

## Тестирование

Стиль проекта (`backend/tests/`, pytest). **Не** db-тесты — чистые юниты.

**Изоляция глобального состояния** (обязательная фикстура): `setup_logging`
мутирует root (`handlers.clear()`) и флаг `_configured`. Без изоляции второй
тест увидит `_configured=True`, а `root.handlers.clear()` снесёт pytest-овский
capture-хендлер и сломает `caplog` в чужих тестах сессии. Фикстура:
- сохранить/восстановить `root.handlers` и `root.level`;
- сбросить `_configured` через monkeypatch;
- `LOG_DIR=tmp_path` (для теста пути), `LOG_TO_FILE=0` для остальных (чтобы
  тесты не плодили файлы).

- **`test_logging_config.py`** (ориентир — CIW `test_logging_config.py`):
  идемпотентность; уровни хендлеров (console=LOG_LEVEL, app.log=DEBUG,
  errors.log=WARNING); `RequestIdFilter` подмешивает `request_id` (дефолт `-`
  без бинда, значение после `bind_request_id`); дефолтный путь = `parents[1]`
  (`backend/logs`); `uvicorn.access` = WARNING и `propagate=True`.
- **`test_middleware.py`** (api): `X-Request-ID` в ответе; переиспользование
  корректного входящего; санитайз (control-символы/длина); генерация при
  отсутствии; строка лога запроса присутствует.

## Что НЕ делаем (YAGNI / отложено)

- `task_id`-корреляция — нет Celery.
- user-в-логах — добавляется одной строкой в новом auth, когда он устаканится.
- JSON-логи / внешний агрегатор — не требуется на этом срезе.
- Настройка логов из Settings — сознательно env-only.

## Порядок реализации (для writing-plans)

1. Пре-флайт: греп `log_level` уже сделан (хиты вне `.venv`: `.env:20`,
   `.env.example:21`, `config.py:15`, `main.py:25`); `logs/` в `.gitignore`
   отсутствует — подтверждено.
2. `app/logging_config.py` + юнит-тест (TDD: тест изоляции первым).
3. `app/middleware.py` + api-тест.
4. Проводка: `main.py`, `config.py`, `seed_vendors.py`, justfile, README,
   `.env.example`/`.env`, `.gitignore`.
5. `just ci` зелёный; девлог после мерджа.
