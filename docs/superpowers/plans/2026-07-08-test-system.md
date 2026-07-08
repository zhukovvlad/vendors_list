# Test System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ввести систему тестов — интеграционные db-тесты БД-логики против Neon, api-тесты роутеров, и каркас vitest на фронте — с прогоном в CI на эфемерной ветке Neon.

**Architecture:** Бэкенд-тесты на pytest + pytest-asyncio; изоляция — одна транзакция на тест с откатом; api-тесты через `httpx.AsyncClient`+`ASGITransport` с подменой зависимостей `read_conn`/`tx`/`require_user`. Фабрики данных — SQLAlchemy Core (без ORM), в два яруса (справочный lookup / незасеянная вставка). Фронт — vitest + testing-library + jsdom.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio (`asyncio_mode=auto`), SQLAlchemy Core (async, asyncpg), httpx, FastAPI; Vitest, @testing-library/react, jsdom; Neon PostgreSQL 18; GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-07-08-test-system-design.md](../specs/2026-07-08-test-system-design.md)

## Global Constraints

- **Ветка работы:** уже на `feat/test-system` (правило CLAUDE.md №7 — в `main` не коммитить, только PR).
- **Схема — источник истины.** Никакого ORM; фабрики — сырой SQL через SQLAlchemy Core (`conn.execute(text(...))`). Две базовые миграции НЕ трогать.
- **Тест-ветка Neon — data+schema** (наследует сиды `0001` и `alembic_version=0002`). Локально URL в `backend/.env` → `DATABASE_URL_TEST` (хвост `?ssl=require`, драйвер asyncpg). Production НЕ трогаем — он уже на `0002_compliance`.
- **`DATABASE_URL_TEST` читаем через `get_settings().database_url_test`** (pydantic читает и `.env`, и env-переменные CI), НЕ через `os.getenv` (иначе `.env` локально не подхватится).
- **db-тесты помечены маркером `db`**; при пустом `DATABASE_URL_TEST` — скипаются (локальный `just ci` без тест-базы остаётся зелёным).
- **Инвертированный TDD для db-тестов:** проверяемая логика (вьюхи/функции/триггеры) уже существует в БД. Тест пишем и ждём **PASS с первого прогона**; FAIL означает ошибку в тесте или в нашем понимании схемы — разбираемся, не «чиним» БД.
- **PowerShell на Windows:** `just` — локально; в CI (ubuntu) `just` НЕ вызывать, alembic/pytest звать напрямую через `uv run`.
- **Проверенные факты схемы** (сверено с `0001`/`0002`): `current_app_user() = coalesce(nullif(current_setting('app.user',true),''), current_user)` — при незаданном `app.user` возвращает роль БД (NOT NULL полей `created_by` не нарушает). Валидные комбинации `listing`: `allowed`→vendor+нет spec_text; `requirement`→нет vendor+spec_text; `not_applicable`/`undefined`→нет vendor. Ячейка `(position_id,segment_id)` — либо вендоры, либо одна мета-строка. Светофор: `manual_check` если нет списка allowed; `open` если список есть, выбора нет; `deviation` если есть вендор вне списка; иначе `compliant`. `compliance_pct = 🟢/(🟢+🔴)`, NULL если судить нечего.

---

## File Structure

**Backend (создать):**
- `backend/tests/__init__.py` — пакет тестов (для импорта `tests.factories`).
- `backend/tests/conftest.py` — фикстуры: skip-хук, `engine`, `db_conn` (откат), `client`, `as_admin`/`as_viewer`, `no_auth_bypass`.
- `backend/tests/factories.py` — SQL-фабрики (два яруса).
- `backend/tests/db/__init__.py`, `backend/tests/db/test_audit.py`, `test_listing_views.py`, `test_compliance.py`, `test_freeze_release.py`.
- `backend/tests/api/__init__.py`, `backend/tests/api/test_projects.py`, `test_listings.py`, `test_releases.py`.

**Backend (изменить):**
- `backend/pyproject.toml` — регистрация маркера `db`.
- `backend/app/config.py` — поля `database_url_test` + `database_url_test_sync`.
- `backend/migrations/env.py` — выбор URL по `MIGRATE_TARGET=test`.
- `backend/.env.example` — строка `DATABASE_URL_TEST=`.
- `justfile` — рецепт `migrate-test`, расширить `test` фронтом.

**Frontend (создать):**
- `frontend/src/test/setup.ts` — подключение матчеров jest-dom.
- `frontend/src/components/ui/button.test.tsx` — стартовый тест рендера.
- `frontend/src/api/client.test.ts` — стартовый тест клиента.

**Frontend (изменить):**
- `frontend/package.json` — dev-deps vitest/testing-library/jsdom, скрипты `test`/`test:watch`.
- `frontend/vite.config.ts` — блок `test`.

**CI (изменить):**
- `.github/workflows/ci.yml` — эфемерная ветка Neon в backend-джобе, `npm run test` во frontend-джобе.

---

## Task 1: Маркер `db` и хук пропуска без тест-БД

**Files:**
- Modify: `backend/pyproject.toml` (секция `[tool.pytest.ini_options]`)
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: существующий `backend/tests/test_smoke.py` + временный db-тест

**Interfaces:**
- Produces: маркер `db`; хук `pytest_collection_modifyitems`, скипающий `db`-тесты при пустом `DATABASE_URL_TEST`.

- [ ] **Step 1: Зарегистрировать маркер `db` в pyproject**

В `backend/pyproject.toml` заменить блок:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "db: интеграционный тест, требует тестовую БД (DATABASE_URL_TEST); пропускается, если URL не задан",
]
```

- [ ] **Step 2: Создать пакет тестов**

Создать `backend/tests/__init__.py` (пустой файл).

- [ ] **Step 3: Создать conftest.py с хуком пропуска**

`backend/tests/conftest.py`:

```python
"""Фикстуры pytest для бэкенд-тестов.

db-тесты (маркер `db`) идут против тестовой ветки Neon (DATABASE_URL_TEST).
Если URL не задан — db-тесты пропускаются, чтобы локальный `just ci` без
тест-базы оставался зелёным. URL читаем через Settings (pydantic видит и .env,
и env-переменные CI), а не через os.getenv.
"""

from __future__ import annotations

import pytest

from app.config import get_settings

TEST_DB_URL = get_settings().database_url_test


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if TEST_DB_URL:
        return
    skip_db = pytest.mark.skip(
        reason="DATABASE_URL_TEST не задан — интеграционные db-тесты пропущены"
    )
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
```

- [ ] **Step 4: Добавить временный db-тест для проверки скипа**

Создать `backend/tests/db/__init__.py` (пустой) и `backend/tests/db/test_marker_smoke.py`:

```python
import pytest

pytestmark = pytest.mark.db


def test_marker_is_registered() -> None:
    assert True
```

- [ ] **Step 5: Прогнать — смоук проходит, db-тест скипается (URL пуст временно)**

Для проверки скипа временно убедиться, что `DATABASE_URL_TEST` не подхватывается (переименовать в `.env` в `DATABASE_URL_TEST_OFF` ЛИБО запустить из каталога без `.env`).

Run: `cd backend; uv run pytest -v`
Expected: `test_smoke.py` — 2 PASS; `test_marker_smoke.py::test_marker_is_registered` — SKIPPED (reason про DATABASE_URL_TEST). Предупреждений о неизвестном маркере нет.

Затем вернуть имя `DATABASE_URL_TEST` в `.env` и повторить:
Expected: тот же тест — PASS (URL задан).

- [ ] **Step 6: Удалить временный тест**

Удалить `backend/tests/db/test_marker_smoke.py` (каталог `db/` и `__init__.py` оставить — пригодятся).

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/tests/__init__.py backend/tests/conftest.py backend/tests/db/__init__.py
git commit -m "test: маркер db и хук пропуска без тестовой БД"
```

---

## Task 2: Тестовый URL в конфиге и `just migrate-test`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/migrations/env.py:24`
- Modify: `backend/.env.example`
- Modify: `justfile`
- Test: `backend/tests/test_config.py` (создать)

**Interfaces:**
- Produces: `Settings.database_url_test: str`, `Settings.database_url_test_sync` (property); `env.py` уважает `MIGRATE_TARGET=test`; рецепт `just migrate-test`.

- [ ] **Step 1: Тест на производный sync-URL**

Создать `backend/tests/test_config.py`:

```python
from app.config import Settings


def test_database_url_test_sync_derivation() -> None:
    s = Settings(
        database_url_test="postgresql+asyncpg://u:p@host/db?ssl=require"
    )
    assert s.database_url_test_sync == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_database_url_test_defaults_empty() -> None:
    s = Settings(database_url_test="")
    assert s.database_url_test == ""
    assert s.database_url_test_sync == ""
```

- [ ] **Step 2: Прогнать — тест падает (поля нет)**

Run: `cd backend; uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`/`ValidationError` (нет `database_url_test`).

- [ ] **Step 3: Добавить поля в Settings**

В `backend/app/config.py` после поля `database_url` (строка 18) добавить:

```python
    # Тестовая ветка Neon (data+schema). Пусто в prod/обычном dev; задаётся
    # в backend/.env локально и в env CI-джобы. Драйвер asyncpg → хвост ssl=require.
    database_url_test: str = ""
```

И после property `database_url_sync` добавить:

```python
    @property
    def database_url_test_sync(self) -> str:
        """Sync-URL (psycopg) для Alembic против тестовой ветки. Пусто, если
        database_url_test не задан. Трансформация — как у database_url_sync."""
        if not self.database_url_test:
            return ""
        url = self.database_url_test.replace("+asyncpg", "+psycopg")
        return url.replace("ssl=require", "sslmode=require")
```

- [ ] **Step 4: Прогнать — тест проходит**

Run: `cd backend; uv run pytest tests/test_config.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Научить env.py целиться в тестовый URL**

В `backend/migrations/env.py` заменить строку 24:

```python
config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)
```

на:

```python
import os  # noqa: E402  (рядом с прочими импортами вверху файла — перенести туда)

_settings = get_settings()
if os.getenv("MIGRATE_TARGET") == "test":
    _url = _settings.database_url_test_sync
    if not _url:
        raise RuntimeError(
            "MIGRATE_TARGET=test, но DATABASE_URL_TEST не задан (backend/.env или env CI)"
        )
else:
    _url = _settings.database_url_sync
config.set_main_option("sqlalchemy.url", _url)
```

(Импорт `os` поднять к остальным импортам в начале файла, убрать инлайн-`import`.)

- [ ] **Step 6: Добавить `DATABASE_URL_TEST=` в backend/.env.example**

В `backend/.env.example` после блока `DATABASE_URL` (после строки 13) вставить:

```
#
# Тестовая ветка Neon (data+schema копия production). Пусто — db-тесты скипаются.
# Хвост ssl=require обязателен (драйвер asyncpg), НЕ sslmode/channel_binding.
DATABASE_URL_TEST=
```

- [ ] **Step 7: Добавить рецепт `migrate-test` в justfile**

В `justfile` после рецепта `migrate` (после строки 29) вставить:

```
# Накатить миграции на ТЕСТОВУЮ ветку (DATABASE_URL_TEST). На data+schema-ветке,
# унаследовавшей alembic_version от production, это no-op (применит только
# реально новые ревизии). Прод не трогает.
migrate-test:
    cd {{backend}}; $env:MIGRATE_TARGET='test'; uv run alembic upgrade head
```

- [ ] **Step 8: Проверить migrate-test против тест-ветки**

Run: `just migrate-test`
Expected: `alembic upgrade head` завершается без ошибок; на data+schema-ветке — «no-op» (никаких `CREATE`; версия уже `0002_compliance`). Если ветка ещё schema-only — см. операционный шаг спеки §6 (пересоздать как data+schema); тогда повторить.

- [ ] **Step 9: Прогнать полный pytest (регрессия)**

Run: `cd backend; uv run pytest -v`
Expected: smoke + test_config — PASS; прочих db-тестов пока нет.

- [ ] **Step 10: Commit**

```bash
git add backend/app/config.py backend/migrations/env.py backend/.env.example justfile backend/tests/test_config.py
git commit -m "test: тестовый DATABASE_URL в конфиге и just migrate-test"
```

---

## Task 3: DB-фикстуры и фабрики

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/factories.py`
- Test: `backend/tests/db/test_fixtures_smoke.py` (создать, затем оставить как реальный тест аудита — см. Task 4; здесь временный)

**Interfaces:**
- Produces:
  - фикстуры (function-scope): `engine` → `AsyncEngine`; `db_conn` → `AsyncConnection` в откатываемой транзакции; `client` → `httpx.AsyncClient` (подменяет `read_conn`/`tx` на `db_conn`); `as_admin`/`as_viewer` → `CurrentUser` (подмена `require_user`); `no_auth_bypass` (выключает dev-bypass для теста 401).
  - `tests/factories.py`: `get_building_type_id(conn, code="residential") -> int`; `get_segment_id(conn, name="Бизнес", building_type_code="residential") -> int`; `make_category(conn, name="Раздел", parent_id=None) -> int`; `make_position(conn, category_id, name="Позиция") -> int`; `make_vendor(conn, name, kind="manufacturer", represents_id=None) -> int`; `make_agreement(conn, vendor_id, status="active") -> int`; `make_listing(conn, position_id, segment_id, vendor_id=None, status="allowed", spec_text=None, sort_order=0) -> int`; `make_release(conn, building_type_id, label="ред. тест", status="open") -> int`; `make_project(conn, code, name, segment_id, release_id=None) -> int`; `make_selection(conn, project_id, position_id, vendor_id, rationale=None, source_ref=None) -> int`.

- [ ] **Step 1: Написать factories.py**

`backend/tests/factories.py`:

```python
"""SQL-фабрики для db-тестов (SQLAlchemy Core, без ORM — правило CLAUDE.md №1).

Два яруса (spec §4.4):
- Справочный (засеян в 0001): building_type / segment_group / segment — LOOKUP
  существующих строк, не вставка (у них уникальные ключи, слепой INSERT упадёт).
- Незасеянный: category / position / vendor / agreement / listing / release /
  project / project_selection — вставка (коллизий нет, изоляция откатом).

Все вставки идут в общее тест-соединение и откатываются в конце теста.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


# --- Справочный ярус: LOOKUP засеянных строк -------------------------------
async def get_building_type_id(conn: AsyncConnection, code: str = "residential") -> int:
    return (
        await conn.execute(
            text("SELECT id FROM building_type WHERE code = :c"), {"c": code}
        )
    ).scalar_one()


async def get_segment_id(
    conn: AsyncConnection,
    name: str = "Бизнес",
    building_type_code: str = "residential",
) -> int:
    return (
        await conn.execute(
            text(
                "SELECT s.id FROM segment s "
                "JOIN building_type bt ON bt.id = s.building_type_id "
                "WHERE bt.code = :bt AND s.name = :n"
            ),
            {"bt": building_type_code, "n": name},
        )
    ).scalar_one()


# --- Незасеянный ярус: вставка ---------------------------------------------
async def make_category(
    conn: AsyncConnection, name: str = "Раздел", parent_id: int | None = None
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO category (name, parent_id) VALUES (:n, :p) RETURNING id"),
            {"n": name, "p": parent_id},
        )
    ).scalar_one()


async def make_position(
    conn: AsyncConnection, category_id: int, name: str = "Позиция"
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO position (category_id, name) VALUES (:c, :n) RETURNING id"),
            {"c": category_id, "n": name},
        )
    ).scalar_one()


async def make_vendor(
    conn: AsyncConnection,
    name: str,
    kind: str = "manufacturer",
    represents_id: int | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO vendor (name, kind, represents_id) "
                "VALUES (:n, :k, :r) RETURNING id"
            ),
            {"n": name, "k": kind, "r": represents_id},
        )
    ).scalar_one()


async def make_agreement(
    conn: AsyncConnection, vendor_id: int, status: str = "active"
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO agreement (vendor_id, status) VALUES (:v, :s) RETURNING id"),
            {"v": vendor_id, "s": status},
        )
    ).scalar_one()


async def make_listing(
    conn: AsyncConnection,
    position_id: int,
    segment_id: int,
    vendor_id: int | None = None,
    status: str = "allowed",
    spec_text: str | None = None,
    sort_order: int = 0,
) -> int:
    """Вставка строки перечня. ВНИМАНИЕ на CHECK listing_status_chk:
    allowed → vendor_id задан, spec_text=None; requirement → vendor_id=None,
    spec_text задан; not_applicable/undefined → vendor_id=None."""
    return (
        await conn.execute(
            text(
                "INSERT INTO listing "
                "(position_id, segment_id, vendor_id, status, spec_text, sort_order) "
                "VALUES (:p, :s, :v, :st, :spec, :ord) RETURNING id"
            ),
            {
                "p": position_id,
                "s": segment_id,
                "v": vendor_id,
                "st": status,
                "spec": spec_text,
                "ord": sort_order,
            },
        )
    ).scalar_one()


async def make_release(
    conn: AsyncConnection,
    building_type_id: int,
    label: str = "ред. тест",
    status: str = "open",
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO release (building_type_id, label, status) "
                "VALUES (:bt, :l, :st) RETURNING id"
            ),
            {"bt": building_type_id, "l": label, "st": status},
        )
    ).scalar_one()


async def make_project(
    conn: AsyncConnection,
    code: str,
    name: str,
    segment_id: int,
    release_id: int | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO compliance.project (code, name, segment_id, release_id) "
                "VALUES (:c, :n, :s, :r) RETURNING id"
            ),
            {"c": code, "n": name, "s": segment_id, "r": release_id},
        )
    ).scalar_one()


async def make_selection(
    conn: AsyncConnection,
    project_id: int,
    position_id: int,
    vendor_id: int,
    rationale: str | None = None,
    source_ref: str | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO compliance.project_selection "
                "(project_id, position_id, vendor_id, rationale, source_ref) "
                "VALUES (:pr, :po, :v, :ra, :sr) RETURNING id"
            ),
            {
                "pr": project_id,
                "po": position_id,
                "v": vendor_id,
                "ra": rationale,
                "sr": source_ref,
            },
        )
    ).scalar_one()
```

- [ ] **Step 2: Дописать DB-фикстуры в conftest.py**

Дополнить `backend/tests/conftest.py` (добавить импорты и фикстуры; хук из Task 1 сохранить):

```python
from collections.abc import AsyncIterator, Iterator

import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth import CurrentUser, require_user
from app.config import Settings, get_settings
from app.db import read_conn, tx
from app.main import app


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Движок на тестовую ветку. NullPool — не держим соединения между тестами,
    заодно уходим от привязки пула к событийному циклу. statement_cache_size=0 —
    обязателен под транзакционный пулер Neon (как в app/db.py)."""
    eng = create_async_engine(
        TEST_DB_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Соединение в откатываемой транзакции: всё, что тест пишет, исчезает в конце."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db_conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент над приложением. read_conn/tx подменены на общее тест-соединение;
    tx-override дополнительно ставит app.user и оборачивает вызов в SAVEPOINT, чтобы
    пойманная роутером ошибка (409/404) откатывала только сбойную операцию, а не всю
    тест-транзакцию (spec §5)."""

    async def _override_read_conn():
        yield db_conn

    async def _override_tx(user: CurrentUser = Depends(require_user)):
        async with db_conn.begin_nested():  # SAVEPOINT
            await db_conn.execute(
                text("SELECT set_config('app.user', :u, true)"),
                {"u": user.username},
            )
            yield db_conn

    app.dependency_overrides[read_conn] = _override_read_conn
    app.dependency_overrides[tx] = _override_tx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    for dep in (read_conn, tx):
        app.dependency_overrides.pop(dep, None)


def _user_override(role: str, username: str):
    def _override() -> CurrentUser:
        return CurrentUser(username=username, role=role)

    return _override


@pytest.fixture
def as_admin() -> Iterator[CurrentUser]:
    app.dependency_overrides[require_user] = _user_override("admin", "admin@test")
    yield CurrentUser(username="admin@test", role="admin")
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture
def as_viewer() -> Iterator[CurrentUser]:
    app.dependency_overrides[require_user] = _user_override("viewer", "viewer@test")
    yield CurrentUser(username="viewer@test", role="viewer")
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture
def no_auth_bypass() -> Iterator[None]:
    """Выключить dev-bypass, чтобы require_user ушёл в реальную проверку токена
    (для теста 401). НЕ app_env='prod' — иначе lifespan кинет RuntimeError."""

    def _override() -> Settings:
        return Settings(auth_dev_bypass=False, app_env="dev")

    app.dependency_overrides[get_settings] = _override
    yield
    app.dependency_overrides.pop(get_settings, None)
```

- [ ] **Step 3: Временный тест, проверяющий фикстуры и оба яруса фабрик**

Создать `backend/tests/db/test_fixtures_smoke.py`:

```python
import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def test_lookup_seeded_reference(db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    assert bt > 0
    assert seg > 0


async def test_insert_and_rollback_tier(db_conn) -> None:
    vid = await f.make_vendor(db_conn, name="Smoke-Vendor")
    got = (
        await db_conn.execute(text("SELECT name FROM vendor WHERE id = :i"), {"i": vid})
    ).scalar_one()
    assert got == "Smoke-Vendor"


async def test_client_health(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
```

- [ ] **Step 4: Прогнать — фикстуры и фабрики работают, изоляция держит**

Run: `cd backend; uv run pytest tests/db/test_fixtures_smoke.py -v`
Expected: 3 PASS. Затем повторный прогон — снова 3 PASS (значит `Smoke-Vendor` не осел в ветке, откат работает). При желании проверить вручную: `Smoke-Vendor` в ветке отсутствует.

- [ ] **Step 5: Удалить временный тест**

Удалить `backend/tests/db/test_fixtures_smoke.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/factories.py
git commit -m "test: db-фикстуры (откат) и SQL-фабрики в два яруса"
```

---

## Task 4: db-тест — аудит-идентичность

**Files:**
- Create: `backend/tests/db/test_audit.py`

**Interfaces:**
- Consumes: `db_conn`, `factories`.

- [ ] **Step 1: Написать тест аудита**

`backend/tests/db/test_audit.py`:

```python
"""Аудит подписывается логином из app.user (SET LOCAL в транзакции).
Логика уже в БД (триггеры *_audit + current_app_user); ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def test_agreement_audit_records_app_user(db_conn) -> None:
    await db_conn.execute(
        text("SELECT set_config('app.user', :u, true)"), {"u": "alice@test"}
    )
    vid = await f.make_vendor(db_conn, name="Audit-Vendor")
    aid = await f.make_agreement(db_conn, vendor_id=vid, status="active")

    changed_by = (
        await db_conn.execute(
            text(
                "SELECT changed_by FROM agreement_change_log "
                "WHERE agreement_id = :a AND action = 'insert'"
            ),
            {"a": aid},
        )
    ).scalar_one()
    assert changed_by == "alice@test"


async def test_listing_created_by_defaults_to_app_user(db_conn) -> None:
    await db_conn.execute(
        text("SELECT set_config('app.user', :u, true)"), {"u": "bob@test"}
    )
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Audit-Listing-V")
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )
    created_by = (
        await db_conn.execute(
            text("SELECT created_by FROM listing WHERE id = :i"), {"i": lid}
        )
    ).scalar_one()
    assert created_by == "bob@test"
```

- [ ] **Step 2: Прогнать — оба PASS с первого раза (логика уже в БД)**

Run: `cd backend; uv run pytest tests/db/test_audit.py -v`
Expected: 2 PASS. Если FAIL — разобраться (ошибка в тесте/понимании), БД не менять.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/db/test_audit.py
git commit -m "test(db): аудит-идентичность через app.user"
```

---

## Task 5: db-тест — вьюха listing_live

**Files:**
- Create: `backend/tests/db/test_listing_views.py`

- [ ] **Step 1: Написать тесты listing_live**

`backend/tests/db/test_listing_views.py`:

```python
"""listing_live: звезда вендора (по активному соглашению), путь раздела,
мета-строка requirement. Логика в БД — ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def test_star_and_category_path(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    root = await f.make_category(db_conn, name="Оборудование")
    cat = await f.make_category(db_conn, name="ОВиК", parent_id=root)
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Grundfos-T")
    await f.make_agreement(db_conn, vendor_id=v, status="active")  # ставит звезду
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )

    row = (
        await db_conn.execute(
            text("SELECT * FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).mappings().one()
    assert row["vendor_starred"] is True
    assert row["category_path"] == "Оборудование / ОВиК"
    assert row["vendor_name"] == "Grundfos-T"


async def test_no_star_without_active_agreement(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Комфорт")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="NoStar-V")
    await f.make_agreement(db_conn, vendor_id=v, status="expired")  # НЕ активно
    lid = await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed"
    )
    starred = (
        await db_conn.execute(
            text("SELECT vendor_starred FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).scalar_one()
    assert starred is False


async def test_requirement_meta_row(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="Сантехника")
    pos = await f.make_position(db_conn, category_id=cat, name="Смесители")
    lid = await f.make_listing(
        db_conn,
        position_id=pos,
        segment_id=seg,
        vendor_id=None,
        status="requirement",
        spec_text="Россия",
    )
    row = (
        await db_conn.execute(
            text("SELECT * FROM listing_live WHERE id = :i"), {"i": lid}
        )
    ).mappings().one()
    assert row["status"] == "requirement"
    assert row["vendor_starred"] is False
    assert row["spec_text"] == "Россия"
    assert row["vendor_name"] is None
```

- [ ] **Step 2: Прогнать — 3 PASS**

Run: `cd backend; uv run pytest tests/db/test_listing_views.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/db/test_listing_views.py
git commit -m "test(db): вьюха listing_live (звезда, путь, requirement)"
```

---

## Task 6: db-тест — светофор и процент соответствия

**Files:**
- Create: `backend/tests/db/test_compliance.py`

- [ ] **Step 1: Написать тесты светофора и compliance_pct**

`backend/tests/db/test_compliance.py`:

```python
"""Светофор compliance.project_position_status и процент project_summary.
Логика в БД — ждём PASS сразу."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _state(db_conn, project_id: int, position_id: int) -> str:
    return (
        await db_conn.execute(
            text(
                "SELECT position_state FROM compliance.project_position_status "
                "WHERE project_id = :p AND position_id = :pos"
            ),
            {"p": project_id, "pos": position_id},
        )
    ).scalar_one()


async def _project_with_allowed(db_conn, seg_name: str, code: str):
    """Проект на классе seg_name + позиция со стандартом (allowed=vendor A)."""
    seg = await f.get_segment_id(db_conn, name=seg_name)
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    allowed = await f.make_vendor(db_conn, name=f"Allowed-{code}")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=allowed, status="allowed"
    )
    proj = await f.make_project(db_conn, code=code, name="Проект", segment_id=seg)
    return seg, pos, allowed, proj


async def test_compliant(db_conn) -> None:
    _, pos, allowed, proj = await _project_with_allowed(db_conn, "Бизнес", "C-1")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=allowed)
    assert await _state(db_conn, proj, pos) == "compliant"


async def test_deviation(db_conn) -> None:
    _, pos, _allowed, proj = await _project_with_allowed(db_conn, "Премиум", "C-2")
    off = await f.make_vendor(db_conn, name="Off-Standard-V")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=off)
    assert await _state(db_conn, proj, pos) == "deviation"


async def test_open(db_conn) -> None:
    _, pos, _allowed, proj = await _project_with_allowed(db_conn, "Комфорт", "C-3")
    assert await _state(db_conn, proj, pos) == "open"


async def test_manual_check_requirement_only(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="Сантехника")
    pos = await f.make_position(db_conn, category_id=cat, name="Трубы")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=None,
        status="requirement", spec_text="ГОСТ",
    )
    proj = await f.make_project(db_conn, code="C-4", name="Проект", segment_id=seg)
    v = await f.make_vendor(db_conn, name="Any-V")
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=v)
    assert await _state(db_conn, proj, pos) == "manual_check"


async def test_compliance_pct_50(db_conn) -> None:
    """1 compliant + 1 deviation → 50.0%."""
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    proj = await f.make_project(db_conn, code="C-5", name="Проект", segment_id=seg)

    pos_ok = await f.make_position(db_conn, category_id=cat, name="Насосы")
    a1 = await f.make_vendor(db_conn, name="Pct-Allowed-1")
    await f.make_listing(db_conn, position_id=pos_ok, segment_id=seg, vendor_id=a1, status="allowed")
    await f.make_selection(db_conn, project_id=proj, position_id=pos_ok, vendor_id=a1)

    pos_dev = await f.make_position(db_conn, category_id=cat, name="Клапаны")
    a2 = await f.make_vendor(db_conn, name="Pct-Allowed-2")
    off = await f.make_vendor(db_conn, name="Pct-Off")
    await f.make_listing(db_conn, position_id=pos_dev, segment_id=seg, vendor_id=a2, status="allowed")
    await f.make_selection(db_conn, project_id=proj, position_id=pos_dev, vendor_id=off)

    pct = (
        await db_conn.execute(
            text("SELECT compliance_pct FROM compliance.project_summary WHERE project_id = :p"),
            {"p": proj},
        )
    ).scalar_one()
    assert float(pct) == 50.0


async def test_compliant_via_brand_key(db_conn) -> None:
    """Вендор-представитель разрешённого бренда = compliant, НЕ deviation.
    Вьюха судит по brand_key = coalesce(represents_id, id): выбор ИСТРАТЕХ
    (represents -> Grundfos) при стандарте Grundfos засчитывается. Самое
    неочевидное правило слоя — «упрощение» brand_key прошло бы мимо остальных
    тестов зелёным."""
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    owner = await f.make_vendor(db_conn, name="Grundfos")  # бренд-владелец в стандарте
    rep = await f.make_vendor(db_conn, name="ИСТРАТЕХ", represents_id=owner)  # представитель
    await f.make_listing(
        db_conn, position_id=pos, segment_id=seg, vendor_id=owner, status="allowed"
    )
    proj = await f.make_project(db_conn, code="C-6", name="Проект", segment_id=seg)
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=rep)

    off = (
        await db_conn.execute(
            text(
                "SELECT off_standard_count FROM compliance.project_position_status "
                "WHERE project_id = :p AND position_id = :pos"
            ),
            {"p": proj, "pos": pos},
        )
    ).scalar_one()
    assert off == 0
    assert await _state(db_conn, proj, pos) == "compliant"
```

- [ ] **Step 2: Прогнать — 6 PASS**

Run: `cd backend; uv run pytest tests/db/test_compliance.py -v`
Expected: 6 PASS (включая `test_compliant_via_brand_key`). Если светофор разошёлся с ожиданием — перечитать вьюху `project_position_status` в `0002`, поправить тест (не БД).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/db/test_compliance.py
git commit -m "test(db): светофор соответствия и compliance_pct"
```

---

## Task 7: db-тест — freeze_release

**Files:**
- Create: `backend/tests/db/test_freeze_release.py`

- [ ] **Step 1: Написать тесты freeze_release**

`backend/tests/db/test_freeze_release.py`:

```python
"""freeze_release: копирует живой перечень в снимок и публикует; повторный
вызов на уже зафиксированном релизе — исключение (инвариант БД)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests import factories as f

pytestmark = pytest.mark.db


async def test_freeze_copies_and_publishes(db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="Freeze-V")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rel = await f.make_release(db_conn, building_type_id=bt, label="ред.1", status="open")

    await db_conn.execute(text("SELECT freeze_release(:r, :a)"), {"r": rel, "a": "editor@test"})

    status_ = (
        await db_conn.execute(text("SELECT status FROM release WHERE id = :r"), {"r": rel})
    ).scalar_one()
    assert status_ == "published"

    snap = (
        await db_conn.execute(
            text("SELECT * FROM release_listing WHERE release_id = :r"), {"r": rel}
        )
    ).mappings().all()
    # Проверяем НАЛИЧИЕ созданной строки, а не общий счётчик: когда появятся
    # боевые листинги (импорт — этап 5), data+schema-ветка их унаследует и
    # residential-снимок может стать больше единицы.
    by_vendor = {r["vendor_name"]: r for r in snap}
    assert "Freeze-V" in by_vendor
    assert by_vendor["Freeze-V"]["vendor_starred"] is True


async def test_freeze_twice_raises(db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="social")
    rel = await f.make_release(db_conn, building_type_id=bt, label="ред.2", status="open")
    await db_conn.execute(text("SELECT freeze_release(:r, NULL)"), {"r": rel})
    # Повторный вызов — статус уже 'published' → RAISE EXCEPTION в функции.
    # Это последняя операция теста: транзакция уходит в aborted, но db_conn
    # всё равно откатывается в teardown (см. spec §5 про SAVEPOINT).
    with pytest.raises(DBAPIError):
        await db_conn.execute(text("SELECT freeze_release(:r, NULL)"), {"r": rel})
```

- [ ] **Step 2: Прогнать — 2 PASS**

Run: `cd backend; uv run pytest tests/db/test_freeze_release.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/db/test_freeze_release.py
git commit -m "test(db): freeze_release (снимок + повторная фиксация)"
```

---

## Task 8: api-тесты — проекты, RBAC, 401/404/409

**Files:**
- Create: `backend/tests/api/__init__.py`
- Create: `backend/tests/api/test_projects.py`

**Interfaces:**
- Consumes: `client`, `as_admin`, `as_viewer`, `no_auth_bypass`, `db_conn`, `factories`.

- [ ] **Step 1: Создать пакет api**

Создать `backend/tests/api/__init__.py` (пустой).

- [ ] **Step 2: Написать api-тесты проектов**

`backend/tests/api/test_projects.py`:

```python
"""API проектов и выбора поверх вьюх. RBAC, коды 201/403/401/404/409.
Записи идут через tx-override (SAVEPOINT) в общее тест-соединение и откатываются."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_create_project_as_admin(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    resp = await client.post(
        "/projects", json={"code": "API-P1", "name": "Проект", "segment_id": seg}
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "API-P1"


async def test_create_project_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    resp = await client.post(
        "/projects", json={"code": "API-P2", "name": "Проект", "segment_id": seg}
    )
    assert resp.status_code == 403


async def test_list_projects_returns_created(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await client.post("/projects", json={"code": "API-P3", "name": "N", "segment_id": seg})
    resp = await client.get("/projects")
    assert resp.status_code == 200
    assert "API-P3" in [p["code"] for p in resp.json()]


async def test_summary_404_for_unknown_project(client, as_admin) -> None:
    resp = await client.get("/projects/999999/summary")
    assert resp.status_code == 404


async def test_duplicate_project_code_409(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await client.post("/projects", json={"code": "API-DUP", "name": "N", "segment_id": seg})
    resp = await client.post(
        "/projects", json={"code": "API-DUP", "name": "N2", "segment_id": seg}
    )
    assert resp.status_code == 409


async def test_projects_requires_auth_401(client, no_auth_bypass) -> None:
    resp = await client.get("/projects")
    assert resp.status_code == 401
```

- [ ] **Step 3: Прогнать — 6 PASS**

Run: `cd backend; uv run pytest tests/api/test_projects.py -v`
Expected: 6 PASS. Особое внимание к 409 (SAVEPOINT в tx-override должен откатить сбойный INSERT, оставив транзакцию живой) и 401 (dev-bypass выключен через `no_auth_bypass`).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/api/__init__.py backend/tests/api/test_projects.py
git commit -m "test(api): проекты, RBAC, 401/404/409"
```

---

## Task 9: api-тесты — listings и releases

**Files:**
- Create: `backend/tests/api/test_listings.py`
- Create: `backend/tests/api/test_releases.py`

- [ ] **Step 1: Написать api-тест listings**

`backend/tests/api/test_listings.py`:

```python
"""GET /listings поверх listing_live: пагинация и фильтр по segment_id."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_listings_page_and_filter(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="List-V")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get("/listings", params={"segment_id": seg})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["limit"] == 100 and body["offset"] == 0
    assert any(r["vendor_name"] == "List-V" for r in body["items"])
```

- [ ] **Step 2: Написать api-тест releases (в т.ч. freeze через API)**

`backend/tests/api/test_releases.py`:

```python
"""POST /releases/{id}/freeze (admin) → снимок в release_listing; 409 на unknown."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_freeze_via_api(client, as_admin, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Премиум")
    cat = await f.make_category(db_conn, name="Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы")
    v = await f.make_vendor(db_conn, name="RelAPI-V")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rel = await f.make_release(db_conn, building_type_id=bt, label="API-ред", status="open")

    resp = await client.post(f"/releases/{rel}/freeze")
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    snap = await client.get(f"/releases/{rel}/listing")
    assert snap.status_code == 200
    # Наличие созданной строки, не общий счётчик (см. пояснение в db-тесте freeze).
    assert any(r["vendor_name"] == "RelAPI-V" for r in snap.json())


async def test_freeze_unknown_release_409(client, as_admin) -> None:
    resp = await client.post("/releases/999999/freeze")
    assert resp.status_code == 409


async def test_freeze_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="social")
    rel = await f.make_release(db_conn, building_type_id=bt, label="V-ред", status="open")
    resp = await client.post(f"/releases/{rel}/freeze")
    assert resp.status_code == 403
```

- [ ] **Step 3: Прогнать все бэкенд-тесты**

Run: `cd backend; uv run pytest -v`
Expected: все PASS (smoke + config + db/* + api/*), 0 FAIL. db-тесты идут (URL задан).

- [ ] **Step 4: Прогнать быстрый путь без БД**

Run: `cd backend; uv run pytest -m "not db" -v`
Expected: только smoke + config PASS; db/api — deselected/не выполняются.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/api/test_listings.py backend/tests/api/test_releases.py
git commit -m "test(api): listings и releases (freeze, RBAC, 409)"
```

---

## Task 10: Каркас vitest на фронте

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/components/ui/button.test.tsx`
- Create: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces: скрипты `npm run test` / `test:watch`; vitest-окружение jsdom.

- [ ] **Step 1: Установить dev-зависимости**

Run:
```
cd frontend; npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```
Expected: пакеты добавлены в `devDependencies`, обновлён `package-lock.json`.

- [ ] **Step 2: Добавить скрипты в package.json**

В `frontend/package.json` в `"scripts"` добавить:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 3: Добавить блок test в vite.config.ts**

В `frontend/vite.config.ts` первой строкой добавить директиву типов и блок `test` в `defineConfig`:

```ts
/// <reference types="vitest/config" />
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
})
```

- [ ] **Step 4: Создать setup.ts**

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest"
```

- [ ] **Step 5: Написать стартовый тест компонента**

`frontend/src/components/ui/button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Button } from "@/components/ui/button"

describe("Button", () => {
  it("рендерит текст и слот-атрибут", () => {
    render(<Button>Сохранить</Button>)
    const btn = screen.getByRole("button", { name: "Сохранить" })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute("data-slot", "button")
  })
})
```

- [ ] **Step 6: Написать стартовый тест клиента API**

`frontend/src/api/client.test.ts`:

```ts
import { describe, expect, it } from "vitest"

import { client } from "@/api/client"

describe("api client", () => {
  it("экспортирует настроенный openapi-fetch клиент", () => {
    expect(client).toBeDefined()
    expect(typeof client.GET).toBe("function")
  })
})
```

Примечание: если фактический экспорт в `client.ts` называется иначе (не `client`) — привести импорт в тесте к реальному имени (сверить `frontend/src/api/client.ts` при исполнении).

- [ ] **Step 7: Прогнать фронт-тесты**

Run: `cd frontend; npm run test`
Expected: 2 файла, 2 PASS.

- [ ] **Step 8: Проверить, что typecheck/lint не сломались**

Run: `cd frontend; npm run typecheck; npm run lint`
Expected: без ошибок (тестовые файлы валидны для tsc/eslint).

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/components/ui/button.test.tsx frontend/src/api/client.test.ts
git commit -m "test(frontend): каркас vitest + стартовые тесты"
```

---

## Task 11: justfile `test` (фронт) и CI на эфемерной ветке Neon

**Files:**
- Modify: `justfile` (рецепт `test`)
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Расширить `just test` фронтом**

В `justfile` заменить рецепт `test` (строки 77-79) на:

```
# Тесты: бэкенд (pytest, db-тесты скипаются без DATABASE_URL_TEST) + фронт (vitest).
test:
    cd {{backend}}; uv run pytest
    cd {{frontend}}; npm run test
```

- [ ] **Step 2: Проверить локально**

Run: `just test`
Expected: pytest — все PASS (db идут, если URL в `.env`); vitest — PASS.

- [ ] **Step 3: Backend-джоба CI — эфемерная ветка Neon**

В `.github/workflows/ci.yml` в джобе `backend` заменить шаг «Tests (pytest)» так, чтобы перед ним создавалась ветка, накатывались миграции, а после — ветка удалялась. Итоговые шаги джобы `backend` (после `uv sync`, `ruff`, `mypy`):

```yaml
      - name: Create Neon test branch
        id: neon
        if: ${{ secrets.NEON_API_KEY != '' }}
        uses: neondatabase/create-branch-action@v5
        with:
          project_id: ${{ secrets.NEON_PROJECT_ID }}
          parent: production
          branch_name: ci-${{ github.run_id }}-${{ github.run_attempt }}
          api_key: ${{ secrets.NEON_API_KEY }}
      - name: Migrate test branch
        if: ${{ steps.neon.outcome == 'success' }}
        env:
          MIGRATE_TARGET: test
          DATABASE_URL_TEST: ${{ steps.neon.outputs.db_url_pooled }}?ssl=require
        run: uv run alembic upgrade head
      - name: Tests (pytest)
        env:
          DATABASE_URL_TEST: ${{ steps.neon.outputs.db_url_pooled != '' && format('{0}?ssl=require', steps.neon.outputs.db_url_pooled) || '' }}
        run: uv run pytest -q
      - name: Delete Neon test branch
        if: ${{ always() && steps.neon.outcome == 'success' }}
        uses: neondatabase/delete-branch-action@v3
        with:
          project_id: ${{ secrets.NEON_PROJECT_ID }}
          branch: ci-${{ github.run_id }}-${{ github.run_attempt }}
          api_key: ${{ secrets.NEON_API_KEY }}
```

Примечания для исполнителя:
- Точные имена выходов экшена (`db_url_pooled`) и версии тегов сверить с README `neondatabase/create-branch-action`/`delete-branch-action` на момент исполнения; при расхождении привести к актуальным.
- На форках без секретов шаг создания скипается (`if: secrets.NEON_API_KEY != ''`), `DATABASE_URL_TEST` пуст → db-тесты скипаются, `pytest` зелёный.
- `just` НЕ используется — раннер ubuntu, justfile PowerShell-only.

- [ ] **Step 4: Frontend-джоба CI — прогон vitest**

В `.github/workflows/ci.yml` в джобе `frontend` после шага «Typecheck (tsc)» и перед «Build» добавить:

```yaml
      - name: Tests (vitest)
        run: npm run test
```

- [ ] **Step 5: Локальная валидация YAML**

Run: `cd backend; uv run python -c "import yaml,sys; yaml.safe_load(open('../.github/workflows/ci.yml', encoding='utf-8')); print('yaml ok')"`
Expected: `yaml ok` (синтаксис workflow валиден).

- [ ] **Step 6: Commit**

```bash
git add justfile .github/workflows/ci.yml
git commit -m "ci: тесты на эфемерной ветке Neon + vitest во фронт-джобе"
```

- [ ] **Step 7: Проверить CI на PR**

Открыть PR из `feat/test-system` в `main` (`gh pr create`), убедиться, что оба джоба зелёные: backend с реально идущими db-тестами (ветка Neon создалась/удалилась), frontend с vitest. Требуются секреты репозитория `NEON_API_KEY`, `NEON_PROJECT_ID`.

---

## Self-Review

**Spec coverage:**
- §4.1 таксономия/маркер `db` → Task 1, структура папок → Tasks 3-9. ✓
- §4.2 тест-БД/изоляция откатом/skip-хук → Tasks 1, 3. ✓
- §4.3 api через ASGITransport, override read_conn/tx/require_user, 401 через get_settings → Tasks 3, 8. ✓
- §4.4 фабрики в два яруса → Task 3; правила `make_listing` → фабрика + Tasks 5-9. ✓
- §4.5 vitest → Task 10. ✓
- §4.6 justfile/CI (alembic напрямую, не just; ветка Neon) → Tasks 2, 11. ✓
- §5 SAVEPOINT (tx-override begin_nested), аудит, freeze 409 → Tasks 3, 7, 8. ✓
- §6 data+schema, migrate-test no-op, пересоздание локальной ветки → Task 2 (Step 8), Global Constraints. ✓
- §7 порядок реализации → порядок задач 1→11. ✓

**Чек-пойнт ревью (из финального замечания заказчика):** при ревью Task 3/4 убедиться, что справочные фабрики (`get_building_type_id`/`get_segment_id`) делают **lookup** засеянных строк, а не пытаются их пересоздать (иначе unique violation). Тест `test_lookup_seeded_reference` это и проверяет.

**Placeholder scan:** код приведён во всех шагах; единственные явные «сверь при исполнении» — реальное имя экспорта в `client.ts` (Task 10 Step 6) и точные выходы/теги Neon-экшенов (Task 11 Step 3), оба помечены и обоснованы (внешние зависимости).

**Type consistency:** имена фабрик и фикстур из Task 3 `Interfaces` используются одинаково в Tasks 4-9; сигнатуры `Settings.database_url_test(_sync)` из Task 2 согласованы с conftest (Task 1/3).
