# CLAUDE.md — рабочие заметки для агента

Приложение учёта вендор-листов и соответствия проектов стандартам.
Заказчик — девелопер. Полное ТЗ: [agent_tasks.md](agent_tasks.md).

## Золотые правила (нарушать нельзя)

1. **БД — источник истины (schema-first).** Схему НЕ генерировать из ORM.
   Полноценный ORM как владелец схемы ЗАПРЕЩЁН (SQLAlchemy ORM, Django ORM,
   Prisma). Используем **SQLAlchemy Core** (async) — см. [backend/app/db.py](backend/app/db.py).
2. **Не дублировать вычислимое в коде.** Светофор соответствия, `compliance_pct`,
   звезда вендора (`vendor_starred`) — только из вьюх/функций БД. API читает
   готовые объекты: `listing_live`, `release_listing`,
   `compliance.project_position_status`, `compliance.project_summary`,
   функцию `freeze_release`.
3. **Пишущие эндпоинты — только через `Depends(tx)`.** Транзакция первым
   делом делает `set_config('app.user', <логин>, is_local=true)` (семантика
   `SET LOCAL`, устойчиво к PgBouncer transaction pooling). Логин — bind-параметром,
   не конкатенацией. Иначе аудит в БД подпишется чужим именем.
4. **Роли — в API, не в БД.** `viewer` (чтение) и `admin` (правки/фиксация/
   соглашения/проекты). Таблицы пользователей/ролей в БД не заводить.
5. **Две базовые миграции неизменны и раздельны.** Ядро и модуль соответствия —
   два независимых SQL-файла в [backend/migrations/sql/](backend/migrations/sql/).
   autogenerate по моделям НЕ использовать. Новые изменения — только новыми
   ревизиями с чистым SQL (`just makemigration name="..."`, затем `op.execute`).
6. **Где живёт логика (тест из ТЗ §6):** «должно ли выполняться, даже если в
   БД напишут в обход API?» Да (инвариант/статус) → в БД миграцией.
   Нет (экран/процесс/интеграция) → в бэкенде.
7. **В `main` не коммитить напрямую.** Любая работа — в отдельной ветке
   (`feat/...`, `fix/...`, `chore/...`), оттуда Pull Request в `main`. `main`
   держим всегда зелёным (проходит `just ci`). Мержим только через PR.
   **Перед пушем — локальный `just ci`** (не ручной набор `npm run …`/`pytest`:
   он недокомплектен относительно CI, напр. без `prettier --check`). Детали —
   [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) §Проверки.
   *Исключение:* правка **только** в `docs/`/Markdown (вкл. `CLAUDE.md`, `README.md`)
   `just ci` не требует — она не касается ни одной проверки (ruff/mypy — backend
   `.py`, prettier/tsc — frontend, pytest/vitest — код). Тронул `.py`/`.ts(x)` или
   конфиг (`pyproject`/`justfile`/`package.json`) — гоняем.

## Стек

- **БД:** PostgreSQL 18 (Neon; схема совместима с 16+, спроектирована на 16).
  Подключение приложения — `DATABASE_URL` в `backend/.env`; для db-тестов —
  отдельный `DATABASE_URL_TEST` (ветка Neon, data+schema).
- **Бэкенд:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy Core (async, asyncpg),
  Alembic (чистый SQL), authlib/pyjwt для OIDC. Менеджер — `uv`.
- **Фронтенд:** Vite + React + TS, shadcn/ui (preset b0, radix) + Tailwind,
  TanStack Table/Query, react-hook-form + Zod.
- **Типизация сквозная:** OpenAPI FastAPI → `openapi-typescript` →
  [frontend/src/api/schema.d.ts](frontend/src/api/schema.d.ts) (`just types`).

## Частые команды (все через just)

```
just install       # установить зависимости бэка и фронта
just migrate       # накатить миграции (ядро + модуль соответствия)
just migrate-test  # миграции на тест-ветку Neon (DATABASE_URL_TEST); на data+schema — no-op
just dev-back      # FastAPI на :8000 (/docs)
just dev-front     # Vite на :5173 (проксирует /api -> :8000)
just types         # перегенерировать TS-типы из OpenAPI
just test          # тесты: backend pytest (+ db-тесты) + фронт vitest
just ci            # все проверки: types, lint, typecheck, test
just seed          # разовый сид 3 стартовых Excel (temp/) в живые таблицы; боевая запись ТОЛЬКО с --yes
just seed-verify   # сухая калибровка парсера на 3 файлах (--dry-run --verify, без БД)
```

Полный список: `just` (без аргументов). Словарь команд унифицирован с
соседним проектом **CIW** (justfile на PowerShell, UTF-8-вывод форсирован).

## Карта репозитория

- `backend/app/` — приложение: `main.py`, `config.py`, `db.py` (движок + tx),
  `auth.py` (OIDC/RBAC), `logging_config.py` (`setup_logging` + `request_id`-корреляция),
  `middleware.py` (ASGI `RequestIdMiddleware`), `routers/` (поверх вьюх), `schemas/` (Pydantic),
  `seed/` (разовый Excel-сид: `parse`/`reader`/`report`/`loader`, см. devlog 2026-07-09).
- `backend/scripts/` — тонкие CLI-шимы: `seed_vendors.py` (сид), `export_openapi.py`.
- `backend/migrations/` — Alembic; `sql/` — два канонических SQL-файла.
- `backend/tests/` — pytest: `conftest.py` (фикстуры: откат-изоляция, ASGI-`client`,
  RBAC-подмена), `factories.py` (SQL-фабрики), `db/` (интеграционные) + `api/` (роутеры);
  сид-юниты `test_seed_{parse,reader,loader,cli}.py` + `db/test_seed_loader.py`.
- `frontend/src/api/` — типизированный клиент (`client.ts`) и хуки Query (`queries.ts`);
  тесты — `*.test.ts(x)` рядом с кодом (vitest).
- `docs/` — [ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVELOPMENT.md](docs/DEVELOPMENT.md),
  [TECH_DEBT.md](docs/TECH_DEBT.md) (реестр осознанно отложенных доработок —
  проверять перед новым срезом и пополнять при отложенных компромиссах),
  [devlog/](docs/devlog/) (хронология работ, файл на задачу — читать при возврате к проекту).
- `temp/` — исходные Excel (3 перечня) и дизайн-хендофф (не трогать без нужды).

## Логирование

Настройка централизована в [`app/logging_config.py`](backend/app/logging_config.py)
(`setup_logging()`, зовётся первой строкой `create_app()`) — руками не переопределять.

- Логгер — `logging.getLogger(__name__)`. **Не** `print`, **не** `logging.basicConfig`
  (снесёт централизованную настройку).
- Новая точка входа мимо `create_app` (CLI/скрипт) — `setup_logging()` первой строкой
  `main()` (образец — [`scripts/seed_vendors.py`](backend/scripts/seed_vendors.py)).
- `request_id` в веб-запросах ставит `RequestIdMiddleware` автоматически (в записи
  подмешивается фильтром, отдаётся как `X-Request-ID`) — руками не биндить.
- `LOG_LEVEL`/`LOG_TO_FILE`/`LOG_DIR` — env-only (`os.getenv`, не Settings, не `.env`):
  задавать реальным env или just-рецептами. Детали —
  [devlog](docs/devlog/2026-07-09-logging-system.md).

## Тесты

- **Backend:** pytest + pytest-asyncio. Маркер `db` = интеграционный тест против
  тест-ветки Neon; без `DATABASE_URL_TEST` такие тесты скипаются (локальный
  `just ci` без тест-базы остаётся зелёным). Изоляция — откат транзакции на тест.
- **Инвертированный TDD для db-тестов:** логика (вьюхи/функции/триггеры) уже в БД —
  ждём PASS с первого прогона; FAIL = ошибка в тесте/понимании схемы, БД НЕ правим.
- **Фабрики** ([backend/tests/factories.py](backend/tests/factories.py)) — сырой SQL
  (без ORM), два яруса: lookup засеянных справочников vs вставка незасеянного.
- **CI:** db-тесты идут на эфемерной ветке Neon (репо-секреты `NEON_API_KEY`/
  `NEON_PROJECT_ID`; без них — скип). Детали —
  [docs/devlog/2026-07-08-test-system.md](docs/devlog/2026-07-08-test-system.md).

## Порядок работ (из ТЗ §5) — где мы

1. ✅ Каркас (репо, CI, миграции, TS-типы, **система тестов**: db/api-тесты, vitest, CI на ветке Neon;
   **дизайн-система (foundation)**: токены/темы/шрифты MR + реколор `button` через переменные shadcn,
   светлая/тёмная — см. [devlog](docs/devlog/2026-07-09-design-system-integration.md);
   **система логирования**: `setup_logging()` (консоль + ротируемые файлы) + чистый ASGI
   `RequestIdMiddleware` (`request_id`/`X-Request-ID`), env-only конфиг `LOG_*` — см.
   [devlog](docs/devlog/2026-07-09-logging-system.md)).
2. ⬜ Транзакционная обёртка есть; SSO/RBAC — каркас есть, нужна боевая интеграция.
3. ⬜ Read-only API есть (listings/releases/compliance); матрица на фронте — TODO.
4. ⬜ Проекты: занесение выбора (API есть), светофор на фронте — TODO.
5. ⬜ Импорт Excel (staging → сверка → коммит), затем экспорт изданий.
   (есть разовый сид `just seed` — грузит 3 стартовых Excel в живые таблицы; запись декомпозирована
   на батч-`executemany` в одной транзакции, реальный прогон ~13k строк ≈ 31с — см.
   [devlog](docs/devlog/2026-07-09-seed-writepath-decomposition.md); интерактивный импорт staging→сверка→коммит и экспорт — впереди)
6. ⬜ Админ-редактирование перечня и изданий.

> UI-фундамент готов; следующий фронт-срез — каталог `card`/`badge`/`table` (несущие
> для матрицы §3 и светофора §4). Отложенный полиш — [docs/TECH_DEBT.md](docs/TECH_DEBT.md).

## Ловушки Excel-импорта (ТЗ §3.4) — помнить при реализации

Неконсистентные написания вендоров, хвостовые пробелы, `*` = соглашение (вести
через `agreement`, в имя не тащить), `(Native)`, объединённые ячейки шапок,
мусорные колонки (один лист сообщает 16384 колонки), лист с датой 2022.
Маппинг вендоров подтверждает человек — не делать импорт полностью авто.

> Разовый сид (`app/seed`) эти ловушки уже разбирает — детали и находки в
> [devlog 2026-07-09](docs/devlog/2026-07-09-excel-seed-import.md). Раздел остаётся
> актуальным для будущего интерактивного импорта §5 (staging → сверка → коммит).
