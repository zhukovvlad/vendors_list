# Дизайн: система тестов (backend + frontend)

**Дата:** 2026-07-08
**Статус:** утверждается (после ревью заказчика)
**Область:** пункт 1 «Порядок работ» из CLAUDE.md — CI/тесты; закрывает пробел
между дымовым тестом и покрытием БД-логики.

---

## 1. Контекст и текущее состояние

- **Backend:** каркас pytest есть (`pytest`, `pytest-asyncio`, `anyio` в dev-deps;
  `asyncio_mode = "auto"`, `testpaths = ["tests"]`). Один файл `test_smoke.py` —
  поднимает приложение, проверяет `/health` и OpenAPI, **в БД не ходит**.
  Тестов, покрывающих БД-логику (вьюхи/функции/триггеры) и API-роутеры, нет.
- **Frontend:** тестового инструментария нет вовсе (ни vitest, ни testing-library,
  ни скрипта `test`). В justfile помечено «vitest — TODO».
- **CI** (`.github/workflows/ci.yml`) гоняет `pytest -q` без `DATABASE_URL` —
  значит БД-тесты сейчас невозможны и должны уметь корректно скипаться.
- **БД:** Neon PostgreSQL 18. Контейнеры и локальный Postgres недоступны —
  тест-БД только Neon.

По золотым правилам CLAUDE.md вся вычислимая логика (светофор, `compliance_pct`,
`vendor_starred`, `freeze_release`) живёт в БД. Значит самый ценный слой тестов —
интеграционные тесты против реального Postgres, проверяющие вьюхи/функции/
инварианты в триггерах и CHECK.

## 2. Цели и не-цели

**Цели:**
- Интеграционные тесты БД-логики против реального Neon.
- Тесты API-роутеров (формы ответов, коды, RBAC viewer/admin, 401/403/404/409).
- Базовый фронтовый харнесс (vitest + testing-library), минимальные стартовые тесты.
- Прогон в CI против эфемерной ветки Neon; локально — против долгоживущей
  ветки `test`.

**Не-цели (YAGNI сейчас):**
- E2E (Playwright) — позже.
- Широкое покрытие фронта — растим вместе с экранами.
- Нагрузочные/property-based тесты.

## 3. Зафиксированные с заказчиком решения

1. **CI-стратегия БД — эфемерная ветка Neon на каждый прогон**, не общая
   фиксированная (общая даёт гонки при параллельных PR; skip убирал бы самый
   ценный слой инвариантов из CI).
2. **Изоляция — одна стратегия: транзакция с откатом.** Без truncate/пересоздания.
   В текущей схеме нет инвариантов, завязанных на `COMMIT` (нет deferred
   constraints, нет межтранзакционной видимости), поэтому вечно-откатываемой
   внешней транзакции достаточно для всего, включая аудит-идентичность.
3. **Skip без URL остаётся** — держит локальный `just ci` зелёным без тест-базы
   и корректно скипает db-тесты на форках (у форков нет секретов Neon).

## 4. Архитектура

### 4.1. Таксономия и структура

```
backend/tests/
  conftest.py            # фикстуры: engine(test-url), соединение-с-откатом,
                         #   client (dep overrides), as_viewer/as_admin
  factories.py           # SQL-хелперы засева (SQLAlchemy Core, без ORM)
  test_smoke.py          # уже есть — без БД, остаётся как есть
  db/                    # интеграционные: бьют в Postgres
    test_compliance.py   #   светофор, compliance_pct, project_position_status,
                         #   project_summary
    test_freeze_release.py
    test_listing_views.py#   listing_live, release_listing
    test_audit.py        #   app.user (set_config) -> current_app_user()
  api/                   # роутеры через httpx + ASGITransport
    test_projects.py     #   CRUD проектов/выбора, RBAC, 401/403/404/409
    test_listings.py
    test_releases.py
```

- Маркер **`db`** на всём, что требует базу. `pytest -m "not db"` — быстрый путь
  (текущий смоук). Маркер **регистрируем** в `pyproject.toml`
  (`[tool.pytest.ini_options] markers = ["db: требует тестовую БД (Neon)"]`),
  иначе pytest ругается на неизвестный маркер.

### 4.2. Тестовая БД и изоляция

- **Локально:** одна долгоживущая ветка `test` (**data+schema**, auto-delete:
  never — см. §6), её **pooled**-URL (`-pooler` в хосте) в `backend/.env` как
  `DATABASE_URL_TEST`.
  Хвост URL — `?ssl=require` (формат asyncpg; `sslmode`/`channel_binding` из
  copy-строки Neon драйвер не понимает — уже исправлено в `.env`).
- **CI:** эфемерная ветка от `production` на прогон (поток — см. 4.6).
- **Изоляция — транзакция с откатом:**
  - сессионная фикстура: `create_async_engine(DATABASE_URL_TEST,
    connect_args={"statement_cache_size": 0})` — `statement_cache_size=0`
    обязателен под транзакционный пулер Neon (как в `db.py`);
  - пофункциональная фикстура: `conn = await engine.connect()`; внешняя
    транзакция `trans = await conn.begin()`; отдаём `conn`; в конце
    `await trans.rollback()`. Ничего не коммитим → ветка не засоряется, тесты
    не зависят от порядка.
- **Skip без URL:** хук `pytest_collection_modifyitems` — если
  `DATABASE_URL_TEST` пуст, вешать `pytest.mark.skip(reason=...)` на всё,
  помеченное `db`.
- `.env.example`: добавить `DATABASE_URL_TEST=` (пустым) с комментарием.

### 4.3. Прогон API-тестов (override зависимостей)

- Клиент — `httpx.AsyncClient` поверх `ASGITransport(app)` (без реального порта).
- Через `app.dependency_overrides` подменяем:
  - `read_conn` и `tx` → **одно и то же** тестовое соединение (из фикстуры);
    override `tx` дополнительно выполняет
    `SELECT set_config('app.user', :user, true)` — чтобы аудит и откат работали
    без коммита.
  - `require_user` → фикстуры `as_viewer` / `as_admin` возвращают нужного
    `CurrentUser` без JWT. RBAC (403 для viewer на пишущих) проверяем реально.
- **Тест 401 — не подделывать `require_user`.** Переопределить зависимость
  `get_settings` на `Settings(auth_dev_bypass=False, app_env="dev")` — тогда
  `require_user` уходит в проверку токена и без креды отдаёт 401.
  - **НЕ** ставить `app_env="prod"`: `lifespan` кидает `RuntimeError`, если в prod
    включён bypass ([main.py:26-27]) — это уронит поднятие приложения.
  - `get_settings` под `@lru_cache` — переопределять именно **зависимость** в
    `dependency_overrides`, а не переменные окружения.

### 4.4. Засев данных (factories)

Маленькие async-хелперы на SQLAlchemy Core, возвращают id. Без ORM/factory-либ
(требование CLAUDE.md, правило №1).

**Два яруса фабрик (следствие data+schema, §6).** На тест-ветке справочники
`building_type`/`segment_group`/`segment` **уже засеяны** из `0001` (3 типа, 11
классов) и защищены уникальными ключами — наивная вставка упадёт на unique
violation:

- `building_type.code` NOT NULL UNIQUE ([0001:39]);
- `segment_group` UNIQUE `(building_type_id, name)` ([0001:51]);
- `segment` UNIQUE `(building_type_id, name)` ([0001:62]).

Поэтому:

- **Засеянный ярус** (`building_type`, `segment_group`, `segment`) — фабрики
  делают **lookup существующей строки** по `code`/`name` (get-or-create), а не
  слепой INSERT. Если тесту нужен изолированный тип — вставлять с заведомо
  уникальным значением (напр. `code=f"test-{uuid}"`). Тесты **не предполагают
  пустые справочники**.
- **Незасеянный ярус** (`category`, `position`, `vendor`, `agreement`, `listing`,
  `release`, `project`, `project_selection`) — свежие INSERT-ы, коллизий нет
  (`category`/`position` уникальных ключей по имени не имеют, сверено).

**Порядок вставки по FK** (ярусы комбинируются): `building_type (lookup) →
segment_group (lookup) → segment (lookup) → category → position → vendor
(→ agreement) → listing`; для соответствия: `release → project (нужны
segment_id, release_id) → project_selection (нужны position_id, vendor_id)`.

**`make_listing` обязана давать валидную комбинацию** — иначе упадёт на CHECK
`listing_status_chk` и триггере `listing_cell_chk`. Проверенные правила из
`0001_core_schema.sql`:

- CHECK: `allowed` → `vendor_id` NOT NULL, `spec_text` NULL;
  `requirement` → `vendor_id` NULL, `spec_text` NOT NULL;
  `not_applicable`/`undefined` → `vendor_id` NULL.
- Триггер + уникальные индексы: ячейка `(position_id, segment_id)` — ЛИБО список
  вендоров (`allowed`), ЛИБО одна мета-строка (requirement/«-»/пусто); смешивать
  нельзя; вендор в живой ячейке не повторяется.

Фабрика по умолчанию делает `allowed` с вендором; для мета-строк — явный вызов
с правильными полями.

### 4.5. Frontend (vitest)

- Dev-зависимости: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`,
  `@testing-library/user-event`, `jsdom`.
- Конфиг тестов в `vite.config.ts`: `test: { environment: "jsdom",
  setupFiles: ["src/test/setup.ts"], globals: true }`. `setup.ts` подключает
  матчеры jest-dom.
- Скрипты `package.json`: `"test": "vitest run"`, `"test:watch": "vitest"`.
- Стартовые тесты (минимум): рендер `Button` + smoke-проверка экспорта
  настроенного клиента (`api.GET` — функция). Тест Query-хука с мок-fetch —
  по мере роста экранов. Дальше растим вместе с ними.

### 4.6. justfile и CI

**justfile (локально, Windows/PowerShell):**
- `just test` → `pytest` (бэк) **+** `npm run test` (фронт).
- `just migrate-test` → `alembic upgrade head` против `DATABASE_URL_TEST`.
  Механизм: добавить в `Settings` поле `database_url_test` и производный
  `database_url_test_sync`; в `migrations/env.py` выбирать тестовый sync-URL при
  `MIGRATE_TARGET=test`. Рецепт: `$env:MIGRATE_TARGET='test'; uv run alembic
  upgrade head`. URL из БД не хардкодим (schema-first, логика URL — в config).
  На ветке типа **data+schema** (см. §6) production уже на `0002_compliance`,
  ветка наследует версию → это честный **no-op** (применит только реально новые
  будущие ревизии).

**CI backend-джоба НЕ вызывает `just`** — justfile PowerShell-only
(`set windows-shell`, `;`, `$env:`), а раннер ubuntu; CI зовёт `uv run …`
напрямую, как и сейчас. Поток:
1. `neondatabase/create-branch-action` → ветка от `production` (**data+schema**,
   дефолт экшена); её pooled-URL → env `DATABASE_URL_TEST` джобы (секреты
   `NEON_API_KEY`, `NEON_PROJECT_ID`). URL нормализовать под asyncpg (`?ssl=require`).
2. `MIGRATE_TARGET=test uv run alembic upgrade head` (bash-форма env, **не**
   `$env:`; **не** `just`). На data+schema-ветке — no-op.
3. `uv run pytest` — **без** `-m "not db"`, чтобы db/api-тесты реально шли.
4. `neondatabase/delete-branch-action` в `if: always()` — снести ветку.
- Шаг создания ветки под `if: ${{ secrets.NEON_API_KEY != '' }}` (или эквивалент):
  на форках секретов нет → `DATABASE_URL_TEST` пуст → db-тесты скипаются, джоба
  **не краснеет**.

**CI frontend-джоба:** добавить шаг `npm run test` (после typecheck).

## 5. Тонкости, на которых легко споткнуться

- **SAVEPOINT под тесты 409/404.** Роутеры ловят `DBAPIError` и отдают 409/404,
  но после ошибки Postgres помечает транзакцию aborted — дальнейшие запросы в том
  же соединении упадут. Если тест после пойманной ошибки ещё читает из БД,
  оборачивать «сбойный» вызов в `begin_nested()` (SAVEPOINT), чтобы откатить
  только его. Тесты с одним пишущим вызовом, проверяющие только код ответа,
  могут обойтись без вложенности.
- **Аудит-идентичность под откатом работает.** Override `tx` ставит `app.user`
  через `set_config(..., true)` на тест-транзакции; `current_app_user()` читает
  её в той же транзакции в момент записи в `*_change_log`; ассерт делаем до
  отката. Отдельная коммитящая ветка не нужна.
- **freeze_release.** Тест: открытый `release` + строки `listing` →
  `freeze_release` → `release_listing` заполнен, статус `published`. Повторный
  вызов на том же релизе → инвариант БД → роутер отдаёт 409 (см. SAVEPOINT, если
  тест продолжает работать с соединением).

## 6. Тип тест-ветки (data+schema)

**Решение: тест-ветки — data+schema (полная копия), не schema-only.**

Разбор наблюдения. Ранняя гипотеза «production заполнялся сырым SQL, версия не
записана» — **неверна**: DEVLOG (2026-07-08) фиксирует «`alembic_version =
0002_compliance`, проверено», т.е. production мигрирован через alembic и версия
на месте. Пустой `alembic_version` на существующей локальной ветке объясняется
иначе — ветка создана **schema-only**: Neon копирует объекты схемы (включая саму
таблицу `alembic_version`), но не её **строку** (это данные). Никакого стемпа
production не требуется — production корректен, трогать его не нужно.

Почему data+schema:

- `0001_core_schema.sql` **сеет справочные данные** INSERT-ами (строки 432-465:
  `building_type`, `segment`, `segment_group` — «3 типа объектов, 11 классов» из
  DEVLOG). data+schema-ветка их наследует; **schema-only — нет** (копируется
  только DDL).
- data+schema наследует и `alembic_version=0002` → `migrate-test`
  (`upgrade head`) — честный **no-op**. schema-only дал бы пустую версию, а
  «мигрировать» пришлось бы через `alembic stamp head` (upgrade упал бы на
  `CREATE TYPE` — в `0001` **ноль** `IF NOT EXISTS`, сверено; править две
  базовые миграции запрещает CLAUDE.md §5), и сиды всё равно не появились бы.
- data+schema — **дефолт** `create-branch-action`; локаль и CI единообразны.
- Минус data+schema (боевые данные production утекают в тесты) сегодня **нулевой**:
  бизнес-данных нет, импорт Excel — этап 5. Когда он появится — пересмотреть
  (варианты: schema-only + явный сид-шаг, либо дисциплина «тесты читают по id из
  фабрик, не полагаются на пустоту таблиц»). Справочные сиды остаются, тесты не
  должны предполагать пустые справочники.

**Операционный шаг (не блокирует код):** существующая локальная ветка —
schema-only (пустой `alembic_version` это подтверждает). Её нужно **пересоздать
как полную (data+schema) копию от production** и вписать pooled-URL в
`DATABASE_URL_TEST`. Действие в консоли/через API Neon — за заказчиком.

## 7. Порядок реализации

1. `conftest.py` (движок на `DATABASE_URL_TEST`, соединение-с-откатом, клиент,
   `as_viewer`/`as_admin`, хук skip-без-URL) и `factories.py`.
2. Правки `Settings`/`env.py` под `migrate-test`; рецепты `just test`/`migrate-test`.
3. Параллельно — CI: create-branch → `alembic upgrade head` (напрямую `uv run`,
   не `just`) → pytest → delete-branch; `npm run test` во frontend-джобе.
4. db-тесты: compliance, freeze_release, listing-вьюхи, audit.
5. api-тесты: projects (+RBAC/401), listings, releases.
6. Frontend: vitest-конфиг, `setup.ts`, стартовые тесты, скрипты.

**Операционный шаг перед реальным прогоном (не перед кодом):** пересоздать
локальную тест-ветку как полную (data+schema) копию от production и вписать её
pooled-URL в `DATABASE_URL_TEST` (см. §6). Стемп production **не нужен** —
production уже на `0002_compliance`.
