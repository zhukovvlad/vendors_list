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

## Стек

- **БД:** PostgreSQL 18 (Neon; схема совместима с 16+, спроектирована на 16).
  Подключение — единственный `DATABASE_URL` в `backend/.env`.
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
just dev-back      # FastAPI на :8000 (/docs)
just dev-front     # Vite на :5173 (проксирует /api -> :8000)
just types         # перегенерировать TS-типы из OpenAPI
just ci            # все проверки: types, lint, typecheck, test
```

Полный список: `just` (без аргументов). Словарь команд унифицирован с
соседним проектом **CIW** (justfile на PowerShell, UTF-8-вывод форсирован).

## Карта репозитория

- `backend/app/` — приложение: `main.py`, `config.py`, `db.py` (движок + tx),
  `auth.py` (OIDC/RBAC), `routers/` (поверх вьюх), `schemas/` (Pydantic).
- `backend/migrations/` — Alembic; `sql/` — два канонических SQL-файла.
- `frontend/src/api/` — типизированный клиент (`client.ts`) и хуки Query (`queries.ts`).
- `docs/` — [ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVELOPMENT.md](docs/DEVELOPMENT.md),
  [devlog/](docs/devlog/) (хронология работ, файл на задачу — читать при возврате к проекту).
- `temp/` — исходные Excel (3 перечня) и дизайн-хендофф (не трогать без нужды).

## Порядок работ (из ТЗ §5) — где мы

1. ✅ Каркас (репо, CI, миграции, генерация TS-типов).
2. ⬜ Транзакционная обёртка есть; SSO/RBAC — каркас есть, нужна боевая интеграция.
3. ⬜ Read-only API есть (listings/releases/compliance); матрица на фронте — TODO.
4. ⬜ Проекты: занесение выбора (API есть), светофор на фронте — TODO.
5. ⬜ Импорт Excel (staging → сверка → коммит), затем экспорт изданий.
6. ⬜ Админ-редактирование перечня и изданий.

## Ловушки Excel-импорта (ТЗ §3.4) — помнить при реализации

Неконсистентные написания вендоров, хвостовые пробелы, `*` = соглашение (вести
через `agreement`, в имя не тащить), `(Native)`, объединённые ячейки шапок,
мусорные колонки (один лист сообщает 16384 колонки), лист с датой 2022.
Маппинг вендоров подтверждает человек — не делать импорт полностью авто.
