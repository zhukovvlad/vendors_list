# 2026-07-08 — Каркас проекта, подключение к Neon, базовые миграции

Развёрнут бойлерплейт по [ТЗ](../../agent_tasks.md), поднято подключение к БД,
накатаны две базовые миграции.

## Сделано

**Backend** (`backend/`, менеджер `uv`, Python 3.12):
- FastAPI поверх готовых объектов БД (расчёты не дублируются): роутеры
  `meta`/`listings`/`releases`/`compliance` читают `listing_live`,
  `release_listing`, `compliance.project_position_status`, `project_summary`.
- [db.py](../../backend/app/db.py): async-движок SQLAlchemy **Core** и две
  зависимости — `read_conn` (чтение) и `tx` (пишущая транзакция с
  идентичностью через `set_config('app.user', :user, true)` = `SET LOCAL`,
  устойчиво к PgBouncer).
- [auth.py](../../backend/app/auth.py): OIDC (JWT по JWKS) + RBAC `viewer`/`admin`,
  dev-bypass.
- Alembic с чистым SQL — две базовые ревизии исполняют канонические `.sql`
  из [migrations/sql/](../../backend/migrations/sql/); autogenerate отключён.

**Frontend** (`frontend/`): создан командой заказчика
`npx shadcn@latest init --preset b0 --base radix --template vite --pointer`;
добавлены TanStack Table/Query, react-hook-form, Zod; типизированный клиент
`openapi-fetch` + сквозные TS-типы из OpenAPI (`just types`), dev-прокси `/api`.

**Инфраструктура:** [justfile](../../justfile) (db/be/fe/types/ci/up), CI
([.github/workflows/ci.yml](../../.github/workflows/ci.yml)), доки
([README](../../README.md), [CLAUDE.md](../../CLAUDE.md),
[ARCHITECTURE](../ARCHITECTURE.md), [DEVELOPMENT](../DEVELOPMENT.md)).

## Ключевые решения

- **Alembic (raw SQL)** вместо dbmate — Python-native, ставится через uv, без
  доп. бинарей.
- **SQLAlchemy Core (async)** вместо asyncpg-raw — пул соединений и
  параметризация `SET LOCAL` из коробки, при этом не ORM (ORM запрещён ТЗ).
- **Одна строка подключения.** В `.env` только `DATABASE_URL` (async);
  sync-URL для Alembic выводится в [config.py](../../backend/app/config.py)
  (`+asyncpg`→`+psycopg`, `ssl=require`→`sslmode=require`). База одна — меньше
  возни, особенно с будущей тестовой БД.
- **`.env.example` по приложениям** (backend/frontend) — секреты БД/SSO
  изолированы от публичных `VITE_*` (те впекаются в бандл).

## Подводные камни (важно для будущих сессий)

- **psycopg3 и `%` в SQL.** Первый `alembic upgrade` упал:
  `only '%s','%b','%t' are allowed as placeholders`. psycopg3 сканирует `%`
  как маркер плейсхолдера даже без параметров, а в SQL полно литеральных `%`
  в `RAISE EXCEPTION '… position %, segment %'`. Лечение — экранирование
  `%`→`%%` в [_sql.py](../../backend/migrations/_sql.py).
- **`alembic.ini` — только ASCII.** Кириллические комментарии ломали configparser
  (читает файл в кодировке ОС, cp1251 на Windows).
- **asyncpg за пулером Neon.** Отключён кэш prepared statements
  (`statement_cache_size=0` в [db.py](../../backend/app/db.py)) — иначе
  «prepared statement already exists».
- **shadcn `button.tsx`** экспортировал `buttonVariants` рядом с компонентом →
  react-refresh. Вынесено в `button-variants.ts` (конфиг eslint не ослабляли).

## Состояние БД

- Инстанс: **Neon, PostgreSQL 18.4**, база `neondb`. Доки обновлены на PG18
  (схема спроектирована на PG16, совместима с 16+).
- Миграции применены: `alembic_version = 0002_compliance`. Проверено — вьюхи
  обоих схем, сиды (3 типа объектов, 11 классов), функции ядра/модуля на месте.

## Что дальше (порядок из ТЗ §5)

Матрица перечня (TanStack Table) → карточка проекта со светофором → занесение
выбора → импорт Excel (staging → сверка через `vendor_alias` + pg_trgm →
коммит) → экспорт изданий → админ-редактирование.

## Открытые хвосты

- Репозиторий не закоммичен (initial commit ждёт отмашки).
- SSO/OIDC — только каркас; нужна боевая интеграция (Entra ID / Keycloak).
