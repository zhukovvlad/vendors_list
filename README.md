# Vendors — учёт вендор-листов и соответствия проектов

Система для девелопера: ведёт перечни одобренных производителей (вендор-листы)
по типам объектов и классам зданий, фиксирует выбор вендоров на проектах и
подсвечивает отступления от стандарта (светофор соответствия).

Полное техническое задание — [agent_tasks.md](agent_tasks.md).
Правила для агента и инварианты — [CLAUDE.md](CLAUDE.md).

## Стек

| Слой        | Технологии |
|-------------|-----------|
| БД          | PostgreSQL 18 (Neon; schema-first, источник истины; совместима с 16+) |
| Бэкенд      | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy **Core** (async, asyncpg), Alembic (чистый SQL), OIDC (authlib/pyjwt) |
| Фронтенд    | Vite + React + TS, shadcn/ui + Tailwind, TanStack Table/Query, react-hook-form + Zod |
| Типизация   | OpenAPI → `openapi-typescript` (сквозные TS-типы) |
| Команды     | `just` |

Ключевой принцип: **бизнес-логику не дублируем**. Светофор, процент
соответствия и звезда вендора приходят из вьюх/функций БД
(`listing_live`, `compliance.project_position_status`, `project_summary`,
`freeze_release`), API лишь читает их.

## Требования

- [just](https://github.com/casey/just), [uv](https://docs.astral.sh/uv/), Node.js 20+ / npm
- PostgreSQL 18 (Neon/облако или локальный кластер; схема совместима с 16+)

## Быстрый старт

```bash
# 1. Зависимости бэкенда и фронтенда
just install

# 2. Настроить окружение (у каждого приложения — свой .env.example)
cp backend/.env.example backend/.env      # заполнить DATABASE_URL (одна строка), OIDC
cp frontend/.env.example frontend/.env    # опционально (в dev не обязательно)

# 3. Создать БД и накатить миграции (ядро + модуль соответствия)
#    БД должна существовать на сервере из DATABASE_URL.
just migrate

# 4. Запуск (в двух терминалах)
just dev-back    # API      -> http://localhost:8000  (Swagger: /docs)
just dev-front   # фронтенд  -> http://localhost:5173
```

В dev по умолчанию включён `AUTH_DEV_BYPASS=true`: запросы идут под фиктивным
пользователем (`AUTH_DEV_USER`, роль `AUTH_DEV_ROLE`) без реального SSO.
В проде bypass ЗАПРЕЩЁН — приложение упадёт при старте, если он включён.

## Полезные команды

```bash
just                        # список всех команд
just migrate                # накатить миграции
just migrate-down           # откатить одну
just makemigration name="x" # новая ПУСТАЯ SQL-ревизия (autogenerate не используем)
just types                  # перегенерировать frontend/src/api/schema.d.ts из OpenAPI
just test                   # тесты бэкенда
just lint                   # ruff + eslint + prettier --check
just ci                     # все проверки (types, lint, typecheck, test)
```

Словарь команд общий с соседним проектом **CIW** (`install`, `migrate`,
`dev-back`, `dev-front`, `lint`, `fmt`, `test`, `build`) — переключаться проще.

## Структура

```
backend/         FastAPI (app/), Alembic (migrations/), 2 канонических SQL
frontend/        Vite + React + shadcn; src/api — типизированный клиент
docs/            ARCHITECTURE.md, DEVELOPMENT.md
temp/            исходные Excel и дизайн-хендофф
```

Подробнее — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) и
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
