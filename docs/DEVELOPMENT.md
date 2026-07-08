# Разработка

## Предпосылки

- `just`, `uv`, Node.js 20+ / npm
- PostgreSQL 18 (dev — Neon; схема совместима с 16+). Docker в системе не
  предполагается — используем готовый кластер, строка подключения в `backend/.env`.

## Настройка окружения

```bash
just install                          # deps бэкенда (uv) + фронтенда (npm)
cp backend/.env.example backend/.env  # заполнить DATABASE_URL (одна строка)
cp frontend/.env.example frontend/.env
```

У каждого приложения свой `.env.example`: секреты БД/SSO живут только в
`backend/` и не соседствуют с публичными `VITE_*` (те впекаются в бандл).
Понятие среды не дублируем: у бэка — `APP_ENV`, у фронта — родной Vite `MODE`.

`backend/.env` (см. [backend/.env.example](../backend/.env.example)):

- `DATABASE_URL` — единственная строка подключения, async-URL приложения:
  `postgresql+asyncpg://user:pass@host:5432/db`. **База одна.** Sync-URL для
  Alembic выводится из неё автоматически (`+asyncpg` → `+psycopg`,
  `ssl=require` → `sslmode=require`) — см. `Settings.database_url_sync` в
  [app/config.py](../backend/app/config.py).
- OIDC-переменные (`OIDC_*`) — для боевого SSO.
- `AUTH_DEV_BYPASS=true` — dev-режим без SSO (в проде обязан быть `false`).

Создайте БД на сервере до миграций:

```sql
CREATE DATABASE vendors;
-- расширение pg_trgm понадобится для нечёткого маппинга вендоров при импорте:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

## Миграции

```bash
just migrate                 # накатить ядро + модуль соответствия
just migrate-current         # текущая ревизия
just migrate-history         # история
just migrate-down            # откатить одну ревизию
just makemigration name="x"  # новая ПУСТАЯ ревизия — правку писать вручную (op.execute)
```

autogenerate не используем. Логика статусов/инвариантов — в SQL, не в моделях.

## Запуск

```bash
just dev-back   # FastAPI :8000, Swagger UI на /docs, ReDoc на /redoc
just dev-front  # Vite :5173 (проксирует /api -> :8000)
```

Оба сервера — в двух терминалах (фронту нужен живой бэк на :8000).

## Сквозные типы

После изменения API-схем пересоберите TS-типы:

```bash
just types    # export OpenAPI -> openapi-typescript -> frontend/src/api/schema.d.ts
```

`schema.d.ts` — генерируемый артефакт (в `.gitignore`); генерируется в CI и
локально. В `frontend/src/api/` пишите только рукописные `client.ts`/`queries.ts`.

## Проверки

```bash
just lint       # ruff + eslint + prettier --check
just typecheck  # mypy (бэк) + tsc (фронт)
just test       # pytest (тесты фронта — vitest — пока не заведены)
just fmt        # ruff --fix + ruff format + prettier --write
just ci          # всё вместе: types, lint, typecheck, test
```

**Финальный прогон перед коммитом/пушем — `just ci`** (не ручной набор
`npm run …`/`pytest`). Ручной набор систематически недокомплектен относительно
CI: например `npm run lint/typecheck/test/build` не включает `prettier --check`,
и CI падает на форматировании там, где локально было «зелено». `just ci` = тот же
набор, что гоняет CI, поэтому ловит расхождения до пуша. Если что-то не так с
форматом — `just fmt` до коммита.

Дымовые тесты бэкенда БД не требуют. Тесты, ходящие в БД, добавляйте с явной
пометкой и отдельной тестовой базой.

## Соглашения

- Бэкенд: ruff (line-length 100) + mypy strict. Импорты сортирует ruff.
- Пишущие эндпоинты — только через `Depends(tx)` и (для правок) `require_admin`.
- Ошибки инвариантов БД (триггеры/CHECK) отдавать как 409 с текстом из БД,
  а не прятать — оператору важно видеть причину.
- Фронтенд: eslint + prettier (конфиги из shadcn-пресета не ослаблять; при
  конфликте с Fast Refresh — выносить не-компоненты в отдельный модуль, как
  сделано с `button-variants.ts`).

## Дальнейшие шаги (ТЗ §5)

Матрица перечня (TanStack Table) → карточка проекта со светофором → занесение
выбора → импорт Excel (staging → сверка через `vendor_alias` + pg_trgm →
коммит) → экспорт изданий → админ-редактирование. См. [../CLAUDE.md](../CLAUDE.md).

Осознанно отложенные доработки (полиш, компромиссы) не держим в голове —
пишем в [TECH_DEBT.md](TECH_DEBT.md) и сверяемся перед новым срезом.
