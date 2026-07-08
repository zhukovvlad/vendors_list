# 2026-07-08 — Система тестов (db-тесты Neon, api-тесты, vitest, CI на эфемерной ветке)

Ветка `feat/test-system` → PR [#1](https://github.com/zhukovvlad/vendors_list/pull/1).
Реализовано по методике subagent-driven-development (план
[docs/superpowers/plans/2026-07-08-test-system.md](../superpowers/plans/2026-07-08-test-system.md),
спека [.../specs/2026-07-08-test-system-design.md](../superpowers/specs/2026-07-08-test-system-design.md)):
11 задач, после каждой — двухстадийное ревью, в конце — ревью всей ветки.

## Что сделано

**Каркас тестов и изоляция** ([backend/tests/](../../backend/tests/)):
- Маркер `db` + хук `pytest_collection_modifyitems`: без `DATABASE_URL_TEST`
  db-тесты скипаются (локальный `just ci` без тест-базы остаётся зелёным).
  URL читаем через `get_settings().database_url_test` (pydantic видит `.env` и env CI),
  НЕ через `os.getenv`.
- Поля `database_url_test` (+ `database_url_test_sync`) в
  [config.py](../../backend/app/config.py); рецепт `just migrate-test`
  (`MIGRATE_TARGET=test`); дефолтные alembic-рецепты защищены от чужого
  `MIGRATE_TARGET` (`$env:MIGRATE_TARGET=''`).
- Async-фикстуры ([conftest.py](../../backend/tests/conftest.py)): `engine`
  (NullPool + `statement_cache_size=0`), `db_conn` (изоляция **откатом
  транзакции**), `client` (ASGI поверх `app` с подменой `read_conn`/`tx`;
  tx-override ставит `app.user` и оборачивает вызов в **SAVEPOINT** —
  пойманная роутером ошибка 409/404 откатывает только сбойную операцию),
  RBAC-фикстуры `as_admin`/`as_viewer`, `no_auth_bypass` (для 401).
- SQL-фабрики ([factories.py](../../backend/tests/factories.py)) в два яруса:
  lookup засеянных справочников (`building_type`/`segment`) и вставка
  незасеянного (category/position/vendor/agreement/listing/release/project/selection).
  Только сырой SQL, без ORM (правило CLAUDE.md №1).

**Интеграционные db-тесты** (инвертированный TDD — логика уже в БД, ждём PASS сразу):
- Аудит-идентичность через `app.user` (триггеры `*_change_log`, `current_app_user()`).
- `listing_live`: звезда по активному соглашению, путь раздела, requirement-строка.
- Светофор `compliance.project_position_status` (compliant/deviation/open/manual_check),
  `compliance_pct`, и правило `brand_key = coalesce(represents_id, id)`
  (вендор-представитель разрешённого бренда = compliant, не deviation).
- `freeze_release`: снимок в `release_listing` + исключение при повторной фиксации.

**api-тесты** (поверх вьюх, через `client`): проекты (RBAC, 201/403/401/404/409),
listings (пагинация/фильтр), releases (freeze через API, 409/403).

**Фронт:** vitest + testing-library + jsdom
([vite.config.ts](../../frontend/vite.config.ts)), стартовые тесты (Button, api-клиент).

**Инфраструктура:** `just test` = pytest + vitest; CI
([.github/workflows/ci.yml](../../.github/workflows/ci.yml)) создаёт эфемерную
ветку Neon (create → migrate → pytest → delete) в backend-джобе, vitest — во frontend-джобе.

## Верификация (выполнена)

- Локально `just ci` — зелёный end-to-end: ruff + eslint + prettier + mypy + tsc
  + backend pytest **29 passed** (реальные db-тесты против ветки Neon) + frontend vitest **2 passed**.
- CI на PR #1 — оба джоба зелёные; backend прошёл **реальный Neon-путь**
  (создал/мигрировал/удалил эфемерную ветку, `29 passed`), не через скип.

## Решения и нюансы (важно для будущих сессий)

- **Порядок исполнения 2→1.** Task 1 (conftest) потребляет `database_url_test`,
  которое добавляет Task 2 (config) — форвардная ссылка. Task 2 выполнен первым;
  границы задач не меняли.
- **CI-секреты — в GitHub, не в `.env`.** `.env` в `.gitignore`, до раннера не
  доходит. Нужны repo secrets `NEON_API_KEY` / `NEON_PROJECT_ID`. См.
  [память проекта](../../CLAUDE.md) — `NEON_PROJECT_ID` это **project id**
  (`autumn-wave-…`), НЕ `ep-…` endpoint id (из-за подмены был первый `404` на create).
- **Neon отдаёт сырой URL.** `db_url_pooled` = `postgresql://…?sslmode=require`
  (без `+asyncpg` — это SQLAlchemy-specific, Neon его не эмитит). Добавлен
  `field_validator` на `database_url_test` в config: любой postgres-URL →
  `postgresql+asyncpg://…?ssl=require` (idempotent, empty-safe; production
  `database_url` не трогаем). Без этого async-движок и psycopg-v3-only зависимости
  падали бы в CI. Проверено реальным прогоном.
- **`secrets` нельзя в GH-Actions `if:`** — вынесены в job-level `env`,
  гейт `if: env.NEON_API_KEY != ''`.
- **`create-branch-action@v6`** переименовал вход `parent` → `parent_branch`
  (v5→v6); output `db_url_pooled` в v6 остался.
- **ruff ловится только полным `just ci`.** Verbatim-код плана дал 2 строки >100
  колонок (E501) в `test_compliance.py`; отдельные прогоны задач гоняли только
  `pytest`, поэтому всплыло на финальном `just ci`. Уложено.

## Что осталось / открытые хвосты

- Пред-существующий `StarletteDeprecationWarning` в
  [test_smoke.py](../../backend/tests/test_smoke.py) (использует
  `fastapi.testclient` = httpx-путь) — не из нашего кода (scaffold); при желании
  почистить отдельной мелкой правкой.
- Возможен осиротевший Neon-branch, если `create-branch-action` частично поднял
  ветку и упал (delete гейтится на `outcome=='success'`). Ветки дешёвые, имена
  уникальные; при накоплении — периодическая чистка.
- PR #1 готов к мержу.
