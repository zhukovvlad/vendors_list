# Архитектура

## Принцип: schema-first

Источник истины — база данных PostgreSQL (dev-инстанс — Neon, PG18; схема
спроектирована и проверена на PG16, совместима с 16+). Схема описана двумя каноническими
SQL-файлами в [../backend/migrations/sql/](../backend/migrations/sql/):

1. `0001_core_schema.sql` — ядро стандартов (схема `public`): справочники
   (типы объектов, классы/группы, дерево разделов, позиции, вендоры + синонимы,
   соглашения), живой перечень `listing` + аудит `change_log`, издания
   `release` + неизменяемые снимки `release_listing`, функция `freeze_release`,
   вьюха `listing_live`.
2. `0002_compliance_module.sql` — модуль соответствия (схема `compliance`):
   проекты, выбор вендоров, светофор `project_position_status`, сводка
   `project_summary`, бренд-ключ `brand_key`.

Инварианты и вычисления (уникальность ячеек, запрет смешивания «вендоры +
требование», статусы светофора, звезда вендора, процент соответствия) живут
**в БД** — триггерами, CHECK-ами, функциями и вьюхами. Приложение их не
дублирует и не «чинит» переносом в код.

## Поток данных

```
PostgreSQL (вьюхи/функции)
        │  SQLAlchemy Core (async, asyncpg)
        ▼
FastAPI routers  ──►  OpenAPI schema
        │                   │  openapi-typescript
        ▼                   ▼
Pydantic v2 (ответы)   frontend/src/api/schema.d.ts
                            │  openapi-fetch (типизированный клиент)
                            ▼
                    React + TanStack Query/Table + shadcn/ui
```

Сквозная типизация без общего рантайма: типы фронта генерируются из OpenAPI
бэкенда (`just types`).

## Бэкенд

- [app/main.py](../backend/app/main.py) — сборка приложения, CORS, монтирование
  роутеров, guard «в проде bypass запрещён».
- [app/db.py](../backend/app/db.py) — async-движок и **две зависимости**:
  - `read_conn` — чтение;
  - `tx` — пишущая транзакция с идентичностью: первым запросом
    `set_config('app.user', :user, true)` (= `SET LOCAL`, устойчиво к
    transaction pooling / PgBouncer), логин передаётся bind-параметром.
    Все пишущие эндпоинты — только через неё.
- [app/auth.py](../backend/app/auth.py) — OIDC (валидация JWT по JWKS издателя)
  и RBAC: `require_user` (viewer+) / `require_admin`. Роли — из claim токена,
  не из БД. В dev — bypass под фиктивным пользователем.
- [app/routers/](../backend/app/routers/) — тонкие роутеры поверх готовых
  объектов БД:
  - `meta` — типы объектов, классы;
  - `listings` — матрица из `listing_live` (серверная пагинация/фильтрация);
  - `releases` — список, выгрузка снимка `release_listing`, `freeze_release` (admin);
  - `compliance` — проекты, светофор, сводка, занесение/удаление выбора (admin).
- [app/schemas/](../backend/app/schemas/) — Pydantic-модели ответов, повторяют
  колонки вьюх.

## Миграции (Alembic, чистый SQL)

`autogenerate` отключён намеренно — схемой владеют SQL-файлы, а не ORM.
Ревизии [0001](../backend/migrations/versions/0001_core_schema.py) и
[0002](../backend/migrations/versions/0002_compliance_module.py) исполняют
соответствующие `.sql` через `exec_driver_sql` (внешние `BEGIN;/COMMIT;`
снимаются — транзакцией управляет сам Alembic). Новые изменения — только новыми
ревизиями с ручным `op.execute`.

## Фронтенд

- [src/api/client.ts](../frontend/src/api/client.ts) — `openapi-fetch` клиент,
  типы из `schema.d.ts`. В dev ходит на `/api` (проксируется Vite на :8000).
- [src/api/queries.ts](../frontend/src/api/queries.ts) — хуки TanStack Query
  (матрица перечня, светофор/сводка проекта).
- shadcn/ui (preset b0, base radix) + Tailwind — базовые компоненты в
  `src/components/ui/`.

### Где живёт компонент (конвенция размещения)

Определяется числом потребителей и природой компонента:

- **Один экран** → рядом с экраном, в `src/screens/<feature>/`. Декомпозиция
  большого экрана на приватные под-компоненты — это норма (колокация): под-часть
  живёт рядом с тем, кто её использует, а не в общем пространстве. Так сейчас
  устроен `screens/vendors/` (`WhereAllowedSection`/`PositionRow`/`ExcludeDialog`
  и пр. — части карточки вендора, не переиспользуются нигде).
- **Два и более экрана, и это НЕ shadcn-примитив** → тогда, и только тогда,
  заводим `src/components/common/` и выносим туда. До появления второго
  потребителя вынос — преждевременное обобщение (напр. `InlineEditText`
  переиспользуем по коду, но пока один потребитель — остаётся в `screens/vendors/`).
- **shadcn/radix-примитив на токенах** → `src/components/ui/`. Эта папка —
  только shadcn/radix; самописное сюда не класть (иначе размывается конвенция
  «ui = shadcn»).
- **Оболочка приложения** (shell, навигация, шапка) → `src/components/layout/`.

Приоритет UI по ТЗ — **просмотр** (большинство пользователей только читают):
матрица перечня и карточка проекта со светофором.

## Роли и безопасность

- `viewer` — любой аутентифицированный: чтение стандартов, изданий, проектов,
  отчётов соответствия.
- `admin` — редактирование стандартов, `freeze_release`, управление
  соглашениями и проектами.

Свою аутентификацию не пишем — токен выдаёт корпоративный SSO/OIDC
(Entra ID / Keycloak), приложение только валидирует подпись и читает роль.
