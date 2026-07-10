# Dashboard «Обзор» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Начальный read-only экран «Обзор» — метрики (Позиции/Издания/Вендоры), список открытых черновиков, очередь «Требует внимания» — сквозным срезом БД→бэкенд→фронт.

**Architecture:** Агрегаты и списки — вьюхи БД (`dashboard_summary`, `dashboard_open_drafts`), читаются одним эндпоинтом `GET /dashboard`. Детект похожих вендоров — прикладной слой (нормализация имён), устойчив к таймауту (`null`, не 500). Фронт — новый экран на `/`, матрица переезжает на `/matrix`.

**Tech Stack:** FastAPI + SQLAlchemy Core (async, asyncpg), Alembic (чистый SQL), PostgreSQL/Neon; Vite + React 19 + TS, TanStack Router/Query, shadcn/ui на MR-токенах, vitest + MSW.

**Spec:** [docs/superpowers/specs/2026-07-10-dashboard-design.md](../specs/2026-07-10-dashboard-design.md)

## Global Constraints

- **БД — источник истины (schema-first).** ORM запрещён; слой данных — SQLAlchemy Core, сырой `text()`. Базовые миграции `0001`/`0002` неизменны — только новые ревизии чистым SQL (`op.execute`), каждая с рабочим `downgrade`.
- **Не дублировать вычислимое в коде.** Счётчики/списки — из вьюх БД; API читает готовое.
- **Экран строго read-only.** Никаких пишущих эндпоинтов, никаких `Depends(tx)`. Действия («Новый стандарт», шевроны) — инертны в этом срезе.
- **Роли:** чтение — `Depends(require_user)`.
- **UI — только русская локализация.** Никакого английского в интерфейсе.
- **DS — семантические токены**, реколор через переменные shadcn. Сырые примитивы (`bg-ink*`, `--color-tan`) в компонентах запрещены. Две темы через класс `.dark`.
- **Адаптивность mobile-first** обязательна.
- **Роутер — TanStack Router** (не react-router).
- **Гейт на каждом таске:** backend-таск — миграция применяется/`pytest` зелёный; frontend-таск — `npm run build` + `npm run lint` + `npm run test`. Перед PR — полный `just ci`.
- **MSW:** `server.listen()` уже висит синхронно в `setup.ts` — не трогать.
- **db-тесты** идут против тест-ветки Neon (маркер `pytest.mark.db`); без `DATABASE_URL_TEST` скипаются. Изоляция — откат транзакции (`db_conn`).

**Ветка:** `feat/dashboard-overview` (уже создана; дизайн-док в ней).

---

## Task 1: DS-токен `warning` (PR-предшественник)

**Files:**
- Modify: `frontend/src/index.css`
- Test: `frontend/src/index.css.test.ts` (Create)

**Interfaces:**
- Produces: CSS-утилиты `text-warning`/`bg-warning`/`border-warning` (Tailwind v4 из `--color-warning`). Значения: light `#9A6636`, dark `#BD9375` (= `--chart-3`).

- [ ] **Step 1: Написать падающий тест (наличие токена в обеих темах)**

Create `frontend/src/index.css.test.ts`:

```ts
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const css = readFileSync(
  fileURLToPath(new URL("./index.css", import.meta.url)),
  "utf-8"
)

describe("warning status token", () => {
  it("объявлен в светлой теме (:root)", () => {
    expect(css).toMatch(/:root\s*\{[^}]*--warning:\s*#9A6636/s)
  })
  it("объявлен в тёмной теме (.dark)", () => {
    expect(css).toMatch(/\.dark\s*\{[^}]*--warning:\s*#BD9375/s)
  })
  it("замаплен в утилиту через @theme inline", () => {
    expect(css).toMatch(/--color-warning:\s*var\(--warning\)/)
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/index.css.test.ts`
Expected: FAIL (токена ещё нет).

- [ ] **Step 3: Добавить токен в три места `index.css`**

В блок `@theme inline { ... }` после `--color-destructive: var(--destructive);` добавить строку:

```css
    --color-warning: var(--warning);
```

В `:root { ... }` после строки `--destructive-foreground: #FFFFFF;` добавить:

```css
    --warning: #9A6636;                    /* статус: предупреждение (= chart-3) */
```

В `.dark { ... }` после `--destructive-foreground: #FFFFFF;` добавить:

```css
    --warning: #BD9375;                    /* статус: предупреждение (= chart-3) */
```

- [ ] **Step 4: Запустить — тест зелёный**

Run: `cd frontend; npx vitest run src/index.css.test.ts`
Expected: PASS.

- [ ] **Step 5: Гейт сборки/линта**

Run: `cd frontend; npm run build; npm run lint; npm run test`
Expected: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/index.css frontend/src/index.css.test.ts
git commit -m "feat(ds): статус-токен warning (light #9A6636 / dark #BD9375)"
```

---

## Task 2: Миграция — вьюхи `dashboard_summary` + `dashboard_open_drafts`

**Files:**
- Create: `backend/migrations/versions/0004_dashboard_views.py`
- Modify: `backend/tests/factories.py` (добавить `make_building_type`, `make_segment`, `make_release_listing`)
- Test: `backend/tests/db/test_dashboard_views.py` (Create)

**Interfaces:**
- Produces:
  - View `dashboard_summary(positions_active int, releases_published int, drafts_open int, vendors_total int, vendors_with_agreement int)` — ровно одна строка.
  - View `dashboard_open_drafts(release_id int, building_type_id int, building_type_name text, label text, last_touched_at timestamptz, last_touched_by text)` — строка на открытый черновик.
  - Factories: `make_building_type(conn, code, name?, sort_order?) -> int`, `make_segment(conn, building_type_id, name, group_id?, sort_order?) -> int`, `make_release_listing(conn, release_id, position_id, status?) -> int`.

- [ ] **Step 1: Добавить фабрики**

В `backend/tests/factories.py` в конец файла добавить:

```python
async def make_building_type(
    conn: AsyncConnection, code: str, name: str = "Тест-тип", sort_order: int = 99
) -> int:
    """Свежий тип объекта (для изоляции агрегатных вьюх — у него нет чужих релизов)."""
    return (
        await conn.execute(
            text(
                "INSERT INTO building_type (code, name, sort_order) "
                "VALUES (:c, :n, :s) RETURNING id"
            ),
            {"c": code, "n": name, "s": sort_order},
        )
    ).scalar_one()


async def make_segment(
    conn: AsyncConnection,
    building_type_id: int,
    name: str = "Тест-класс",
    group_id: int | None = None,
    sort_order: int = 0,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO segment (building_type_id, group_id, name, sort_order) "
                "VALUES (:bt, :g, :n, :o) RETURNING id"
            ),
            {"bt": building_type_id, "g": group_id, "n": name, "o": sort_order},
        )
    ).scalar_one()


async def make_release_listing(
    conn: AsyncConnection, release_id: int, position_id: int, status: str = "allowed"
) -> int:
    """Минимальная строка снимка издания (release_listing без триггеров)."""
    return (
        await conn.execute(
            text(
                "INSERT INTO release_listing (release_id, position_id, status) "
                "VALUES (:r, :p, :st) RETURNING id"
            ),
            {"r": release_id, "p": position_id, "st": status},
        )
    ).scalar_one()
```

- [ ] **Step 2: Написать падающие db-тесты (вьюх ещё нет)**

Create `backend/tests/db/test_dashboard_views.py`:

```python
"""Вьюхи дашборда: dashboard_summary (агрегаты) и dashboard_open_drafts.

Вьюхи глобальны (считают ВСЮ базу) — тестируем ДЕЛЬТУ от базовой линии на
свежесозданных данных, а не абсолютные числа (БД засеяна)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _summary(db_conn) -> dict:
    return (
        (await db_conn.execute(text("SELECT * FROM dashboard_summary"))).mappings().one()
    )


async def test_positions_active_from_latest_published_snapshot(db_conn) -> None:
    base = (await _summary(db_conn))["positions_active"]
    bt = await f.make_building_type(db_conn, code="pa-bt")
    cat = await f.make_category(db_conn, name="pa-cat")
    p1 = await f.make_position(db_conn, category_id=cat, name="pa-p1")
    p2 = await f.make_position(db_conn, category_id=cat, name="pa-p2")
    rid = await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release_listing(db_conn, release_id=rid, position_id=p1)
    await f.make_release_listing(db_conn, release_id=rid, position_id=p2)
    await f.make_release_listing(db_conn, release_id=rid, position_id=p2)  # дубль → distinct=2
    assert (await _summary(db_conn))["positions_active"] == base + 2


async def test_latest_published_deterministic_on_equal_dates(db_conn) -> None:
    # Два published с ОДИНАКОВОЙ датой; побеждает больший id (страховка детерминизма).
    base = (await _summary(db_conn))["positions_active"]
    bt = await f.make_building_type(db_conn, code="det-bt")
    cat = await f.make_category(db_conn, name="det-cat")
    p_old = await f.make_position(db_conn, category_id=cat, name="det-old")
    p_extra = await f.make_position(db_conn, category_id=cat, name="det-extra")
    p_new = await f.make_position(db_conn, category_id=cat, name="det-new")
    r1 = await f.make_release(db_conn, building_type_id=bt, status="published")
    r2 = await f.make_release(db_conn, building_type_id=bt, status="published")
    await db_conn.execute(
        text("UPDATE release SET effective_date = DATE '2026-01-01' WHERE id IN (:a, :b)"),
        {"a": r1, "b": r2},
    )
    await f.make_release_listing(db_conn, release_id=r1, position_id=p_old)
    await f.make_release_listing(db_conn, release_id=r1, position_id=p_extra)  # r1 → 2
    await f.make_release_listing(db_conn, release_id=r2, position_id=p_new)     # r2 → 1
    # r2.id > r1.id ⇒ выбран r2 ⇒ этот тип даёт 1, не 2.
    assert (await _summary(db_conn))["positions_active"] == base + 1


async def test_vendors_brandkey_and_agreement(db_conn) -> None:
    base = await _summary(db_conn)
    owner = await f.make_vendor(db_conn, name="BK-Owner")
    await f.make_vendor(db_conn, name="BK-Sub", represents_id=owner)  # тот же бренд
    after_add = await _summary(db_conn)
    assert after_add["vendors_total"] == base["vendors_total"] + 1  # sub схлопнут
    assert after_add["vendors_with_agreement"] == base["vendors_with_agreement"]
    await f.make_agreement(db_conn, vendor_id=owner, status="active")
    after_agr = await _summary(db_conn)
    assert after_agr["vendors_with_agreement"] == base["vendors_with_agreement"] + 1


async def test_release_status_counts_exclude_archived(db_conn) -> None:
    base = await _summary(db_conn)
    bt = await f.make_building_type(db_conn, code="rc-bt")
    await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release(db_conn, building_type_id=bt, status="open")
    await f.make_release(db_conn, building_type_id=bt, status="archived")
    after = await _summary(db_conn)
    assert after["releases_published"] == base["releases_published"] + 1
    assert after["drafts_open"] == base["drafts_open"] + 1  # archived НЕ считается


async def test_open_drafts_only_open_visible(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od-bt")
    rid_pub = await f.make_release(db_conn, building_type_id=bt, status="published")
    rid_open = await f.make_release(db_conn, building_type_id=bt, status="open")
    ids = {
        r["release_id"]
        for r in (
            await db_conn.execute(text("SELECT release_id FROM dashboard_open_drafts"))
        ).mappings()
    }
    assert rid_open in ids and rid_pub not in ids


async def test_open_drafts_last_touched_fallback_to_created_at(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od2-bt")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")  # без правок listing
    row = (
        await db_conn.execute(
            text("SELECT last_touched_at FROM dashboard_open_drafts WHERE release_id = :r"),
            {"r": rid},
        )
    ).mappings().one()
    assert row["last_touched_at"] is not None  # fallback = release.created_at


async def test_open_drafts_last_touched_from_listing(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="od3-bt")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="od3-seg")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")
    cat = await f.make_category(db_conn, name="od3-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="od3-pos")
    v = await f.make_vendor(db_conn, name="od3-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    row = (
        await db_conn.execute(
            text(
                "SELECT last_touched_at, last_touched_by "
                "FROM dashboard_open_drafts WHERE release_id = :r"
            ),
            {"r": rid},
        )
    ).mappings().one()
    assert row["last_touched_at"] is not None
    assert row["last_touched_by"] is not None  # current_app_user() из вставки listing
```

- [ ] **Step 3: Запустить — убедиться, что падают (relation does not exist)**

Run: `cd backend; uv run pytest tests/db/test_dashboard_views.py -q`
Expected: FAIL/ERROR — `relation "dashboard_summary" does not exist`.
(Если нет `DATABASE_URL_TEST` — тесты скипнутся; тогда прогнать после настройки тест-ветки.)

- [ ] **Step 4: Подтвердить головную ревизию и имена колонок, затем написать миграцию**

Сначала убедиться, что цепочка ревизий не разъедется:

Run: `cd backend; uv run alembic heads`
Expected: единственный head `0003_category_sort_path` — тогда `down_revision = "0003_category_sort_path"` верен. Если head другой/несколько — привести `down_revision` к фактическому head.

Имена колонок `release` для вьюхи `dashboard_open_drafts` подтверждены по
[0001:312-315](../../../backend/migrations/sql/0001_core_schema.sql#L312-L315):
`label` (NOT NULL), `effective_date` (nullable), `author` (nullable) — существуют.

Create `backend/migrations/versions/0004_dashboard_views.py`:

```python
"""Ревизия №4: вьюхи дашборда «Обзор» (презентация, read-only).

dashboard_summary   — одна строка скалярных агрегатов (позиции в действующих
                      релизах, счётчики изданий, вендоры по бренд-ключу).
dashboard_open_drafts — открытые черновики с последней правкой (last_touched).
Инвариантов не добавляет. is_stale здесь НЕ считается — порог задаётся в запросе.

Revision ID: 0004_dashboard_views
Revises: 0003_category_sort_path
"""

from __future__ import annotations

from alembic import op

revision = "0004_dashboard_views"
down_revision = "0003_category_sort_path"
branch_labels = None
depends_on = None

_UP = """
CREATE VIEW dashboard_summary AS
WITH current_release AS (
    SELECT DISTINCT ON (building_type_id) id
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC
),
brands AS (
    SELECT DISTINCT coalesce(represents_id, id) AS brand_id FROM vendor
)
SELECT
    (SELECT count(DISTINCT rl.position_id)
       FROM release_listing rl
       JOIN current_release cr ON cr.id = rl.release_id
      WHERE rl.position_id IS NOT NULL)                        AS positions_active,
    (SELECT count(*) FROM release WHERE status = 'published')  AS releases_published,
    (SELECT count(*) FROM release WHERE status = 'open')       AS drafts_open,
    (SELECT count(*) FROM brands)                              AS vendors_total,
    (SELECT count(*) FROM brands WHERE vendor_starred(brand_id)) AS vendors_with_agreement;

CREATE VIEW dashboard_open_drafts AS
SELECT
    r.id                                    AS release_id,
    r.building_type_id,
    bt.name                                 AS building_type_name,
    r.label,
    coalesce(la.last_at, r.created_at)      AS last_touched_at,
    coalesce(la.last_by, r.author)          AS last_touched_by
FROM release r
JOIN building_type bt ON bt.id = r.building_type_id
LEFT JOIN LATERAL (
    SELECT max(l.updated_at) AS last_at,
           (array_agg(l.updated_by ORDER BY l.updated_at DESC))[1] AS last_by
    FROM listing l
    JOIN segment s ON s.id = l.segment_id
    WHERE s.building_type_id = r.building_type_id
      AND l.deleted_at IS NULL
) la ON true
WHERE r.status = 'open';
"""

_DOWN = """
DROP VIEW IF EXISTS dashboard_open_drafts;
DROP VIEW IF EXISTS dashboard_summary;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
```

- [ ] **Step 5: Применить миграцию на тест-ветку**

Run: `just migrate-test`
Expected: `Running upgrade 0003_category_sort_path -> 0004_dashboard_views`.

- [ ] **Step 6: Запустить db-тесты — зелёные**

Run: `cd backend; uv run pytest tests/db/test_dashboard_views.py -q`
Expected: PASS (все).

- [ ] **Step 7: Проверить обратимость миграции**

Run: `just migrate-down`  затем  `just migrate-test`
Expected: `downgrade` снимает вьюхи без ошибок, повторный `upgrade` их возвращает.

- [ ] **Step 8: Commit**

```bash
git add backend/migrations/versions/0004_dashboard_views.py backend/tests/db/test_dashboard_views.py backend/tests/factories.py
git commit -m "feat(db): вьюхи dashboard_summary + dashboard_open_drafts (0004)"
```

---

## Task 3: Конфиг `dashboard_stale_days`

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py` (Modify)

**Interfaces:**
- Produces: `Settings.dashboard_stale_days: int = 14` (env `DASHBOARD_STALE_DAYS`).

- [ ] **Step 1: Написать падающий тест**

В `backend/tests/test_config.py` добавить:

```python
def test_dashboard_stale_days_default() -> None:
    from app.config import Settings

    assert Settings().dashboard_stale_days == 14


def test_dashboard_stale_days_from_env(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("DASHBOARD_STALE_DAYS", "7")
    assert Settings().dashboard_stale_days == 7
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend; uv run pytest tests/test_config.py -q -k dashboard_stale`
Expected: FAIL (`AttributeError`/валидация).

- [ ] **Step 3: Добавить поле в `Settings`**

В `backend/app/config.py` в класс `Settings` после `cors_origins: str = ...` добавить:

```python
    # Порог «залежавшегося» черновика (дни) для дашборда. Правится env, не миграцией.
    dashboard_stale_days: int = 14
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend; uv run pytest tests/test_config.py -q -k dashboard_stale`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(config): порог dashboard_stale_days (default 14, env)"
```

---

## Task 4: Детект кандидатов на объединение (прикладной слой)

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/dashboard.py`
- Test: `backend/tests/test_dashboard_service.py` (Create, unit), `backend/tests/db/test_dashboard_service.py` (Create, db)

**Interfaces:**
- Produces:
  - `normalize_vendor_name(name: str) -> str` — чистая нормализация.
  - `async count_merge_candidates(conn: AsyncConnection, *, timeout_ms: int = 1500) -> int | None` — число кандидат-пар; `None` при провале/таймауте.

- [ ] **Step 1: Написать падающий unit-тест нормализации**

Create `backend/tests/test_dashboard_service.py`:

```python
from app.services.dashboard import normalize_vendor_name


def test_normalize_collapses_case_space_punct() -> None:
    assert normalize_vendor_name("  Grundfos ") == "grundfos"
    assert normalize_vendor_name("Wilo-Pumpen") == normalize_vendor_name("wilo pumpen")


def test_normalize_strips_native_tail() -> None:
    assert normalize_vendor_name("WILO (Native)") == normalize_vendor_name("wilo")
```

- [ ] **Step 2: Запустить — падает (модуля нет)**

Run: `cd backend; uv run pytest tests/test_dashboard_service.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Создать сервис**

Create `backend/app/services/__init__.py` (пустой):

```python
"""Прикладные сервисы: логика процесса/интеграции, не инварианты БД."""
```

Create `backend/app/services/dashboard.py`:

```python
"""Дашборд: прикидочный детект похожих вендоров (гигиена справочника).

Нормализация/схлопывание брендов живёт в прикладном слое (не в БД). Кандидат-пара =
коллизия нормализованного имени между разными бренд-ключами. Триграммы — отложены.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# Убираем только ОБЩИЙ хвост «(Native)» — не любые скобки. Скобки с брендом-
# владельцем («ИСТРАТЕХ (Grundfos)») разрешаются через represents_id в данных, а не
# нормализацией имени; срезать все скобки нельзя — «Насос (300Вт)» и «(500Вт)»
# схлопнулись бы в ложный дубль. Детект консервативный: пропуск лучше шума.
_TAIL = re.compile(r"\((?:native|нативный)\)", re.IGNORECASE)
_NONALNUM = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


def normalize_vendor_name(name: str) -> str:
    """lower + убрать общий хвост «(Native)» + схлопнуть пунктуацию/пробелы.

    НЕ трогает скобки с брендом-владельцем — это забота represents_id, не регэкспа."""
    s = _TAIL.sub(" ", name).lower()
    s = _NONALNUM.sub(" ", s)
    return " ".join(s.split())


async def count_merge_candidates(
    conn: AsyncConnection, *, timeout_ms: int = 1500
) -> int | None:
    """Число кандидат-пар (коллизия нормы между разными бренд-ключами).

    Устойчив к таймауту: SET LOCAL statement_timeout + перехват DBAPIError → None
    (медленный детект не должен ронять весь дашборд).

    SET LOCAL действует ТОЛЬКО внутри транзакции. read_conn в SQLAlchemy 2.0 (без
    AUTOCOMMIT) транзакционен, и к вызову коннект уже в неявной транзакции запроса
    (сводка/черновики прочитаны раньше) — таймаут применяется к SELECT ниже и
    сбрасывается при закрытии соединения (без утечки в пул). Если транзакции всё же
    нет (изменится порядок вызовов) — открываем и откатываем свою (детект read-only),
    чтобы гарантия таймаута не зависела от того, «кто открыл транзакцию раньше»."""
    own_txn = not conn.in_transaction()
    if own_txn:
        await conn.begin()
    try:
        await conn.execute(
            text("SELECT set_config('statement_timeout', :ms, true)"),
            {"ms": str(timeout_ms)},
        )
        rows = (
            await conn.execute(
                text("SELECT coalesce(represents_id, id) AS brand_id, name FROM vendor")
            )
        ).mappings().all()
    except DBAPIError:
        logger.warning("merge-candidate detect failed/timed out", exc_info=True)
        return None
    finally:
        if own_txn and conn.in_transaction():
            await conn.rollback()  # закрыть СВОЮ транзакцию → сбросить statement_timeout

    by_norm: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        by_norm[normalize_vendor_name(r["name"])].add(r["brand_id"])

    pairs = 0
    for brand_ids in by_norm.values():
        n = len(brand_ids)
        if n >= 2:
            pairs += n * (n - 1) // 2  # число пар среди схлопнувшихся брендов
    return pairs
```

- [ ] **Step 4: Запустить unit-тест — зелёный**

Run: `cd backend; uv run pytest tests/test_dashboard_service.py -q`
Expected: PASS.

- [ ] **Step 5: Написать падающий db-тест детекта**

Create `backend/tests/db/test_dashboard_service.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.services import dashboard as svc
from app.services.dashboard import count_merge_candidates
from tests import factories as f

pytestmark = pytest.mark.db


async def test_norm_collision_between_brands_is_candidate(db_conn) -> None:
    base = await count_merge_candidates(db_conn)
    await f.make_vendor(db_conn, name="ZzBrand")
    await f.make_vendor(db_conn, name="zz brand")  # та же норма, другой бренд-ключ
    assert await count_merge_candidates(db_conn) == base + 1


async def test_linked_vendors_not_candidate(db_conn) -> None:
    base = await count_merge_candidates(db_conn)
    owner = await f.make_vendor(db_conn, name="YyBrand")
    await f.make_vendor(db_conn, name="yy brand", represents_id=owner)  # тот же бренд-ключ
    assert await count_merge_candidates(db_conn) == base  # не пара


async def test_local_statement_timeout_is_effective(db_conn) -> None:
    # Доказательство пункта ревью №1: SET LOCAL statement_timeout РЕАЛЬНО действует в
    # read-транзакции (db_conn уже в транзакции). Иначе защита в count_merge_candidates
    # была бы фикцией. 50 мс + pg_sleep(1) → отмена запроса.
    await db_conn.execute(text("SELECT set_config('statement_timeout', '50', true)"))
    with pytest.raises(DBAPIError):
        await db_conn.execute(text("SELECT pg_sleep(1)"))
    # транзакция после отмены — в aborted; фикстура db_conn откатит её в teardown.


async def test_returns_none_on_internal_db_error(db_conn, monkeypatch) -> None:
    # Пункт ревью №2: ВНУТРЕННЯЯ защита (except DBAPIError → None), а не только
    # роутерный except. SELECT vendor «падает» DBAPIError → функция сама вернёт None.
    orig = db_conn.execute
    state = {"n": 0}

    async def flaky(clause, *args, **kwargs):
        state["n"] += 1
        if state["n"] >= 2:  # 1-й вызов — set_config; 2-й — SELECT vendor → взрыв
            raise OperationalError("SELECT vendor", {}, Exception("simulated timeout"))
        return await orig(clause, *args, **kwargs)

    monkeypatch.setattr(db_conn, "execute", flaky)
    assert await svc.count_merge_candidates(db_conn) is None
```

- [ ] **Step 6: Запустить db-тест — зелёный**

Run: `cd backend; uv run pytest tests/db/test_dashboard_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services backend/tests/test_dashboard_service.py backend/tests/db/test_dashboard_service.py
git commit -m "feat(dashboard): детект кандидатов на объединение (норм-коллизия, timeout→None)"
```

---

## Task 5: Эндпоинт `GET /dashboard`

**Files:**
- Modify: `backend/app/schemas/__init__.py` (схемы дашборда)
- Create: `backend/app/routers/dashboard.py`
- Modify: `backend/app/routers/__init__.py`, `backend/app/main.py` (регистрация)
- Test: `backend/tests/db/test_dashboard_api.py` (Create), `backend/tests/api/test_dashboard.py` (Create)

**Interfaces:**
- Consumes: `dashboard_summary`, `dashboard_open_drafts` (Task 2); `count_merge_candidates` (Task 4); `Settings.dashboard_stale_days` (Task 3).
- Produces: `GET /dashboard -> Dashboard{summary: DashboardSummary, drafts: list[DashboardDraft]}`.

- [ ] **Step 1: Добавить схемы**

В `backend/app/schemas/__init__.py` в конец файла добавить:

```python
# --- Дашборд «Обзор» --------------------------------------------------------
class DashboardSummary(BaseModel):
    positions_active: int
    releases_published: int
    drafts_open: int
    vendors_total: int
    vendors_with_agreement: int
    merge_candidate_pairs: int | None  # None ⇒ детект не отработал (не 500)


class DashboardDraft(BaseModel):
    model_config = _from_row
    release_id: int
    building_type_name: str
    label: str
    last_touched_at: datetime
    last_touched_by: str | None
    is_stale: bool


class Dashboard(BaseModel):
    summary: DashboardSummary
    drafts: list[DashboardDraft]
```

- [ ] **Step 2: Написать падающие db/api-тесты эндпоинта**

Create `backend/tests/db/test_dashboard_api.py`:

```python
"""GET /dashboard: форма ответа, is_stale по порогу, деградация детекта."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_shape(client, as_viewer) -> None:
    body = (await client.get("/dashboard")).json()
    assert set(body) == {"summary", "drafts"}
    assert set(body["summary"]) == {
        "positions_active",
        "releases_published",
        "drafts_open",
        "vendors_total",
        "vendors_with_agreement",
        "merge_candidate_pairs",
    }
    assert isinstance(body["drafts"], list)


async def test_stale_flag_by_threshold(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="st-bt")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")
    # состарить черновик: created_at на 100 дней назад (правок listing нет → fallback)
    from sqlalchemy import text

    await db_conn.execute(
        text("UPDATE release SET created_at = now() - interval '100 days' WHERE id = :r"),
        {"r": rid},
    )
    drafts = {d["release_id"]: d for d in (await client.get("/dashboard")).json()["drafts"]}
    assert drafts[rid]["is_stale"] is True


async def test_merge_detect_failure_degrades_not_500(client, as_viewer, monkeypatch) -> None:
    from app.routers import dashboard as dash

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(dash, "count_merge_candidates", _boom)
    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    assert resp.json()["summary"]["merge_candidate_pairs"] is None
```

Create `backend/tests/api/test_dashboard.py`:

```python
"""GET /dashboard: контракт авторизации."""

import pytest

pytestmark = pytest.mark.db


async def test_requires_auth(client, no_auth_bypass) -> None:
    resp = await client.get("/dashboard")
    assert resp.status_code == 401
```

- [ ] **Step 3: Запустить — падают (эндпоинта нет → 404)**

Run: `cd backend; uv run pytest tests/db/test_dashboard_api.py tests/api/test_dashboard.py -q`
Expected: FAIL (404 вместо 200/401).

- [ ] **Step 4: Написать роутер**

Create `backend/app/routers/dashboard.py`:

```python
"""GET /dashboard — сводка начального экрана поверх вьюх dashboard_*.

Строго read-only. is_stale считается здесь по :stale_days из конфига (не в теле
вьюхи). merge_candidate_pairs — из прикладного детекта; его сбой деградирует в
null, а не в 500 на весь экран.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_user
from ..config import Settings, get_settings
from ..db import read_conn
from ..schemas import Dashboard, DashboardDraft, DashboardSummary
from ..services.dashboard import count_merge_candidates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard, dependencies=[Depends(require_user)])
async def get_dashboard(
    conn: AsyncConnection = Depends(read_conn),
    settings: Settings = Depends(get_settings),
) -> Dashboard:
    summary_row = (
        await conn.execute(text("SELECT * FROM dashboard_summary"))
    ).mappings().one()

    draft_rows = (
        await conn.execute(
            text(
                "SELECT release_id, building_type_name, label, "
                "last_touched_at, last_touched_by, "
                "(last_touched_at < now() - make_interval(days => :d)) AS is_stale "
                "FROM dashboard_open_drafts ORDER BY last_touched_at DESC"
            ),
            {"d": settings.dashboard_stale_days},
        )
    ).mappings().all()

    try:
        pairs = await count_merge_candidates(conn)
    except Exception:  # noqa: BLE001 — детект НЕ должен ронять экран
        logger.warning("merge-candidate detect raised; degrading to null", exc_info=True)
        pairs = None

    return Dashboard(
        summary=DashboardSummary(**dict(summary_row), merge_candidate_pairs=pairs),
        drafts=[DashboardDraft.model_validate(dict(r)) for r in draft_rows],
    )
```

- [ ] **Step 5: Зарегистрировать роутер**

В `backend/app/routers/__init__.py`:

```python
"""API-роутеры. Читают из готовых вьюх/таблиц БД; расчёты не дублируют."""

from . import compliance, dashboard, listings, meta, releases

__all__ = ["compliance", "dashboard", "listings", "meta", "releases"]
```

В `backend/app/main.py` заменить строку импорта и цикл включения:

```python
from .routers import compliance, dashboard, listings, meta, releases
```

```python
    for module in (meta, listings, releases, compliance, dashboard):
        app.include_router(module.router)
```

- [ ] **Step 6: Запустить — тесты зелёные**

Run: `cd backend; uv run pytest tests/db/test_dashboard_api.py tests/api/test_dashboard.py -q`
Expected: PASS.

- [ ] **Step 7: Перегенерировать TS-типы (контракт для фронта)**

Run: `just types`
Expected: `frontend/src/api/schema.d.ts` содержит путь `/dashboard` и схемы `Dashboard`/`DashboardSummary`/`DashboardDraft` (файл gitignored — не коммитим).

- [ ] **Step 8: Гейт бэкенда целиком**

Run: `cd backend; uv run pytest -q; uv run ruff check .; uv run mypy app`
Expected: зелёное.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/dashboard.py backend/app/routers/__init__.py backend/app/main.py backend/tests/db/test_dashboard_api.py backend/tests/api/test_dashboard.py
git commit -m "feat(api): GET /dashboard (summary + drafts, is_stale из конфига, детект→null)"
```

---

## Task 6: DS-компонент `skeleton`

**Files:**
- Create: `frontend/src/components/ui/skeleton.tsx`, `frontend/src/components/ui/skeleton.test.tsx`

**Interfaces:**
- Produces: `<Skeleton className? />` — плейсхолдер загрузки на токене `bg-accent` (темизирован).

- [ ] **Step 1: Написать падающий тест**

Create `frontend/src/components/ui/skeleton.test.tsx`:

```tsx
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Skeleton } from "./skeleton"

describe("Skeleton", () => {
  it("рендерит плейсхолдер с анимацией и токен-фоном (не сырой примитив)", () => {
    const { container } = render(<Skeleton className="h-4 w-10" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain("animate-pulse")
    expect(el.className).toContain("bg-accent")
    expect(el.className).toContain("h-4")
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/components/ui/skeleton.test.tsx`
Expected: FAIL (модуля нет).

- [ ] **Step 3: Создать компонент**

Добавить через shadcn (или создать файл вручную с этим содержимым — итог должен использовать токен `bg-accent`):

Run (опционально): `cd frontend; npx --yes shadcn@latest add skeleton`

Гарантированное содержимое `frontend/src/components/ui/skeleton.tsx`:

```tsx
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("bg-accent animate-pulse rounded-md", className)}
      {...props}
    />
  )
}

export { Skeleton }
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd frontend; npx vitest run src/components/ui/skeleton.test.tsx`
Expected: PASS.

- [ ] **Step 5: Гейт**

Run: `cd frontend; npm run build; npm run lint`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/skeleton.tsx frontend/src/components/ui/skeleton.test.tsx
git commit -m "feat(ds): компонент skeleton (bg-accent, для загрузки дашборда)"
```

---

## Task 7: Модель экрана (`model.ts`) — чистые хелперы

**Files:**
- Create: `frontend/src/screens/dashboard/model.ts`, `frontend/src/screens/dashboard/model.test.ts`

**Interfaces:**
- Consumes: типы `components["schemas"]["Dashboard"]` (из `schema.d.ts`, Task 5).
- Produces: `formatRelative(iso: string, now: Date) -> string`, `hasAttention(d: Dashboard) -> boolean`, реэкспорт типов `Dashboard`/`DashboardDraft`/`DashboardSummary`.

- [ ] **Step 1: Написать падающий тест**

Create `frontend/src/screens/dashboard/model.test.ts`:

```ts
import { describe, expect, it } from "vitest"

import { formatRelative, hasAttention } from "./model"
import type { Dashboard } from "./model"

const NOW = new Date("2026-07-10T12:00:00Z")

function iso(daysAgo: number): string {
  return new Date(NOW.getTime() - daysAgo * 86_400_000).toISOString()
}

describe("formatRelative", () => {
  it("сегодня / вчера / дни / недели с русским склонением", () => {
    expect(formatRelative(iso(0), NOW)).toBe("сегодня")
    expect(formatRelative(iso(1), NOW)).toBe("вчера")
    expect(formatRelative(iso(3), NOW)).toBe("3 дня назад")
    expect(formatRelative(iso(14), NOW)).toBe("2 недели назад")
  })
})

describe("hasAttention", () => {
  const base: Dashboard = {
    summary: {
      positions_active: 0,
      releases_published: 0,
      drafts_open: 0,
      vendors_total: 0,
      vendors_with_agreement: 0,
      merge_candidate_pairs: 0,
    },
    drafts: [],
  }

  it("false, когда кандидатов нет и нет залежавшихся", () => {
    expect(hasAttention(base)).toBe(false)
  })

  it("true, если есть кандидаты", () => {
    expect(hasAttention({ ...base, summary: { ...base.summary, merge_candidate_pairs: 6 } })).toBe(
      true
    )
  })

  it("null кандидатов трактуется как «нет пункта»", () => {
    expect(
      hasAttention({ ...base, summary: { ...base.summary, merge_candidate_pairs: null } })
    ).toBe(false)
  })

  it("true, если есть залежавшийся черновик", () => {
    const stale: Dashboard["drafts"][number] = {
      release_id: 1,
      building_type_name: "Жилые",
      label: "v1",
      last_touched_at: iso(30),
      last_touched_by: "a@b",
      is_stale: true,
    }
    expect(hasAttention({ ...base, drafts: [stale] })).toBe(true)
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/screens/dashboard/model.test.ts`
Expected: FAIL (модуля нет).

- [ ] **Step 3: Создать модель**

Create `frontend/src/screens/dashboard/model.ts`:

```ts
import type { components } from "@/api/schema"

export type Dashboard = components["schemas"]["Dashboard"]
export type DashboardDraft = components["schemas"]["DashboardDraft"]
export type DashboardSummary = components["schemas"]["DashboardSummary"]

function plural(n: number, forms: [string, string, string]): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return forms[0]
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1]
  return forms[2]
}

/** Относительное время правки: «сегодня» / «вчера» / «N дней|недель назад». */
export function formatRelative(iso: string, now: Date): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return "сегодня"
  if (days === 1) return "вчера"
  if (days < 7) return `${days} ${plural(days, ["день", "дня", "дней"])} назад`
  const weeks = Math.floor(days / 7)
  return `${weeks} ${plural(weeks, ["неделю", "недели", "недель"])} назад`
}

/** Есть ли что показать в «Требует внимания» (кандидаты или залежавшиеся). */
export function hasAttention(d: Dashboard): boolean {
  const pairs = d.summary.merge_candidate_pairs
  return (pairs != null && pairs > 0) || d.drafts.some((x) => x.is_stale)
}
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd frontend; npx vitest run src/screens/dashboard/model.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/dashboard/model.ts frontend/src/screens/dashboard/model.test.ts
git commit -m "feat(dashboard): чистые хелперы model.ts (formatRelative, hasAttention)"
```

---

## Task 8: Хук данных `useDashboard` + MSW-хендлер

**Files:**
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/test/msw/handlers.ts`

**Interfaces:**
- Produces: `useDashboard()` (TanStack Query поверх `GET /dashboard`); экспорт `dashboardFixture` из хендлеров для тестов экрана.

- [ ] **Step 1: Добавить хук**

В `frontend/src/api/queries.ts` в конец файла добавить:

```ts
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => {
      const { data, error } = await api.GET("/dashboard")
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /dashboard")
      return data
    },
  })
}
```

- [ ] **Step 2: Добавить MSW-хендлер и фикстуру**

В `frontend/src/test/msw/handlers.ts`: добавить экспорт фикстуры и хендлер в массив `handlers`.

Перед `export const handlers = [`:

```ts
export const dashboardFixture = {
  summary: {
    positions_active: 412,
    releases_published: 18,
    drafts_open: 3,
    vendors_total: 248,
    vendors_with_agreement: 142,
    merge_candidate_pairs: 6,
  },
  drafts: [
    {
      release_id: 1,
      building_type_name: "Жилой дом",
      label: "Бизнес v4",
      last_touched_at: "2026-07-09T10:00:00Z",
      last_touched_by: "ivanov",
      is_stale: false,
    },
    {
      release_id: 3,
      building_type_name: "Соцобъект",
      label: "Базовый v2",
      last_touched_at: "2026-06-25T10:00:00Z",
      last_touched_by: "petrov",
      is_stale: true,
    },
  ],
}
```

Внутри массива `handlers` добавить элемент:

```ts
  http.get(`${BASE}/dashboard`, () => HttpResponse.json(dashboardFixture)),
```

- [ ] **Step 3: Гейт (типы + сборка)**

Run: `cd frontend; npm run typecheck; npm run test`
Expected: зелёное (существующие тесты не сломаны; `schema.d.ts` уже содержит `/dashboard` из Task 5).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/test/msw/handlers.ts
git commit -m "feat(dashboard): хук useDashboard + MSW-фикстура"
```

---

## Task 9: Роутинг — дашборд на `/`, матрица на `/matrix`

**Files:**
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/router.test.tsx` (Create)

**Interfaces:**
- Consumes: `DashboardScreen` (Task 10 — на момент правки роутера создать заглушку-плейсхолдер, заменяемую в Task 10).
- Produces: маршрут `/` → `dashboardRoute`; `/matrix` → `matrixRoute`; `/design-system` без изменений. `routeTree` экспортируется по-прежнему.

- [ ] **Step 1: Написать падающий тест роутинга**

Create `frontend/src/router.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createRouter,
  createMemoryHistory,
} from "@tanstack/react-router"
import { describe, expect, it } from "vitest"

import { routeTree } from "./router"

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>
  )
}

describe("routing", () => {
  it("/ рендерит дашборд «Обзор»", async () => {
    renderAt("/")
    await waitFor(() => expect(screen.getByText("Обзор")).toBeInTheDocument())
  })

  it("/matrix рендерит экран матрицы (фильтр «Тип объекта»)", async () => {
    renderAt("/matrix")
    await waitFor(() =>
      expect(screen.getByText("Тип объекта")).toBeInTheDocument()
    )
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/router.test.tsx`
Expected: FAIL (нет маршрута `/matrix` / дашборда).

- [ ] **Step 3: Создать заглушку экрана (заменится в Task 10)**

Create `frontend/src/screens/dashboard/DashboardScreen.tsx`:

```tsx
export function DashboardScreen() {
  return <div className="p-6 text-foreground">Обзор</div>
}
```

- [ ] **Step 4: Перенастроить роутер**

В `frontend/src/router.tsx`:

Добавить импорт рядом с прочими экранами:

```tsx
import { DashboardScreen } from "@/screens/dashboard/DashboardScreen"
```

Изменить `path` матрицы с `"/"` на `"/matrix"`:

```tsx
export const matrixRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/matrix",
```

В `loader` матрицы поменять редирект-цель `to: "/"` на `to: "/matrix"`:

```tsx
        throw redirect({
          to: "/matrix",
          search: (prev) => ({ ...prev, building_type_id: first.id }),
        })
```

Добавить маршрут дашборда (индекс `/`) перед `designSystemRoute`:

```tsx
const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardScreen,
})
```

Включить его в дерево:

```tsx
export const routeTree = rootRoute.addChildren([
  dashboardRoute,
  matrixRoute,
  designSystemRoute,
])
```

- [ ] **Step 5: Запустить — зелёный**

Run: `cd frontend; npx vitest run src/router.test.tsx`
Expected: PASS.

- [ ] **Step 6: Прогнать существующие тесты матрицы (не сломаны переносом)**

Run: `cd frontend; npm run test`
Expected: PASS (MatrixScreen-тесты строят memory-router из `routeTree` — маршрут теперь `/matrix`, но тесты используют `matrixRoute` напрямую; при падении из-за пути — обновить initialEntries в затронутом тесте на `/matrix`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/router.tsx frontend/src/router.test.tsx frontend/src/screens/dashboard/DashboardScreen.tsx
git commit -m "feat(routing): дашборд на /, матрица на /matrix"
```

---

## Task 10: Экран `DashboardScreen` (метрики, черновики, внимание, скелетоны, адаптив)

**Files:**
- Modify: `frontend/src/screens/dashboard/DashboardScreen.tsx`
- Test: `frontend/src/screens/dashboard/DashboardScreen.test.tsx` (Create)

**Interfaces:**
- Consumes: `useDashboard` (Task 8), `formatRelative`/`hasAttention` (Task 7), `Card`/`Skeleton` DS.

- [ ] **Step 1: Написать падающие тесты экрана**

Create `frontend/src/screens/dashboard/DashboardScreen.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "@/test/msw/server"
import { dashboardFixture } from "@/test/msw/handlers"

import { DashboardScreen } from "./DashboardScreen"

function renderScreen() {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <DashboardScreen />
    </QueryClientProvider>
  )
}

describe("DashboardScreen", () => {
  it("показывает три метрики с числами", async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText("412")).toBeInTheDocument())
    expect(screen.getByText("248")).toBeInTheDocument()
    expect(screen.getByText(/142/)).toBeInTheDocument()
  })

  it("список черновиков и залежавшийся в «Требует внимания»", async () => {
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText(/Жилой дом/)).toBeInTheDocument()
    )
    expect(screen.getByText(/Соцобъект/)).toBeInTheDocument()
    expect(screen.getByText(/6 пар вендоров/)).toBeInTheDocument()
  })

  it("«всё чисто», когда внимания не требуется", async () => {
    server.use(
      http.get("/api/dashboard", () =>
        HttpResponse.json({
          summary: { ...dashboardFixture.summary, merge_candidate_pairs: 0 },
          drafts: [
            { ...dashboardFixture.drafts[0], is_stale: false },
          ],
        })
      )
    )
    renderScreen()
    await waitFor(() => expect(screen.getByText(/всё чисто/i)).toBeInTheDocument())
  })

  it("скелетоны на время загрузки (до ответа)", () => {
    const { container } = (() => {
      const qc = new QueryClient()
      return render(
        <QueryClientProvider client={qc}>
          <DashboardScreen />
        </QueryClientProvider>
      )
    })()
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/screens/dashboard/DashboardScreen.test.tsx`
Expected: FAIL (заглушка печатает только «Обзор»).

- [ ] **Step 3: Реализовать экран**

Заменить содержимое `frontend/src/screens/dashboard/DashboardScreen.tsx`:

```tsx
import { ChevronRight, LockOpen, Users, ArrowsUpFromLine } from "lucide-react"

import { useDashboard } from "@/api/queries"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

import { formatRelative, hasAttention } from "./model"

function Metric({
  label,
  value,
  children,
}: {
  label: string
  value: number
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-caption uppercase text-muted-foreground">{label}</div>
        <div className="mt-1 text-h3 font-medium">{value}</div>
        <div className="mt-2 text-small text-muted-foreground">{children}</div>
      </CardContent>
    </Card>
  )
}

export function DashboardScreen() {
  const now = new Date()
  const { data, isLoading, isError } = useDashboard()

  if (isError) {
    return <div className="p-6 text-destructive">Ошибка загрузки обзора.</div>
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-3 p-6">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <CardContent className="pt-4">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-2 h-7 w-16" />
                <Skeleton className="mt-3 h-3 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  const { summary, drafts } = data
  const staleDrafts = drafts.filter((d) => d.is_stale)
  const attention = hasAttention(data)

  return (
    <div className="flex flex-col gap-3 p-6 text-foreground">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h3 font-medium">Обзор</h1>
          <div className="text-small text-muted-foreground">Ведение вендор-листов</div>
        </div>
        {/* Действие отложено: цель (создание стандарта) — будущий срез. */}
        <Button disabled title="Скоро">
          Новый стандарт
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Позиции" value={summary.positions_active}>
          в действующих релизах
        </Metric>
        <Metric label="Издания" value={summary.releases_published + summary.drafts_open}>
          {summary.releases_published} релизов · {summary.drafts_open} черновика
        </Metric>
        <Metric label="Вендоры" value={summary.vendors_total}>
          <span className="flex items-center gap-1">
            <Users className="size-3" /> {summary.vendors_with_agreement} с соглашением
          </span>
        </Metric>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardContent className="pt-4">
            <div className="mb-1 text-caption uppercase text-muted-foreground">
              Черновики в работе
            </div>
            {drafts.length === 0 ? (
              <div className="py-4 text-small text-muted-foreground">
                Открытых черновиков нет.
              </div>
            ) : (
              drafts.map((d) => (
                <div
                  key={d.release_id}
                  className="flex items-center gap-3 border-t border-border py-3"
                >
                  <LockOpen className="size-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-small">
                      {d.building_type_name} · {d.label}
                    </div>
                    <div className="text-caption text-muted-foreground">
                      изменён {formatRelative(d.last_touched_at, now)}
                      {d.last_touched_by ? ` · ${d.last_touched_by}` : ""}
                    </div>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="mb-1 text-caption uppercase text-muted-foreground">
              Требует внимания
            </div>
            {!attention ? (
              <div className="py-4 text-small text-muted-foreground">Всё чисто.</div>
            ) : (
              <>
                {summary.merge_candidate_pairs != null &&
                  summary.merge_candidate_pairs > 0 && (
                    <div className="flex items-center gap-3 border-t border-border py-3">
                      <ArrowsUpFromLine className="size-4 shrink-0 text-primary" />
                      <div className="min-w-0 flex-1 text-small">
                        {summary.merge_candidate_pairs} пар вендоров похожи
                        <div className="text-caption text-muted-foreground">
                          возможные дубли
                        </div>
                      </div>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </div>
                  )}
                {staleDrafts.map((d) => (
                  <div
                    key={d.release_id}
                    className="flex items-center gap-3 border-t border-border py-3"
                  >
                    <LockOpen className="size-4 shrink-0 text-warning" />
                    <div className="min-w-0 flex-1 text-small">
                      {d.building_type_name} · {d.label} залежался
                      <div className="text-caption text-muted-foreground">
                        черновик не менялся давно
                      </div>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd frontend; npx vitest run src/screens/dashboard/DashboardScreen.test.tsx`
Expected: PASS. (Если иконочного имени нет в `lucide-react` — заменить на существующее, напр. `GitMerge`/`Merge`; проверить `npm run build`.)

- [ ] **Step 5: Гейт фронта целиком**

Run: `cd frontend; npm run build; npm run lint; npm run test`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/dashboard/DashboardScreen.tsx frontend/src/screens/dashboard/DashboardScreen.test.tsx
git commit -m "feat(dashboard): экран «Обзор» (метрики/черновики/внимание, скелетоны, адаптив)"
```

---

## Task 11: Финализация — `just ci`, devlog, документация, PR

**Files:**
- Modify: `CLAUDE.md` (§5), `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-10-dashboard-overview.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли` (types, lint, typecheck, test — backend+frontend).
Если `DATABASE_URL_TEST` задан локально — db-тесты дашборда идут; если нет — скип (нормально), но CI на PR прогонит на эфемерной ветке Neon.

- [ ] **Step 2: Devlog**

Create `docs/devlog/2026-07-10-dashboard-overview.md` — кратко: что сделано (вьюхи `dashboard_*`, `GET /dashboard`, детект дублей, экран `/`, перенос матрицы на `/matrix`, токен `warning`, skeleton), ключевые решения (Позиции = снимок последнего published; бренд-ключ; is_stale из конфига; детект→null), ссылки на спеку и план.

- [ ] **Step 3: Обновить CLAUDE.md §5 и карту**

В `CLAUDE.md` в разделе «Порядок работ» отметить дашборд как сделанный срез; в «Карту репозитория» добавить `screens/dashboard/`, `app/services/dashboard.py`, вьюхи `dashboard_*`, роут `/` (дашборд) / `/matrix` (матрица).

- [ ] **Step 4: TECH_DEBT**

В `docs/TECH_DEBT.md` внести: (1) триграммный fuzzy-детект дублей (v1 — только норм-коллизия); (2) вынос `merge_candidate_pairs` в ленивый эндпоинт при тяжёлом детекте; (3) токен `success` — завести при первом позитивном статусе; (4) активация отложенных действий дашборда («Новый стандарт», шевроны) при появлении экранов-целей.

- [ ] **Step 5: Commit + push + PR**

```bash
git add CLAUDE.md docs/TECH_DEBT.md docs/devlog/2026-07-10-dashboard-overview.md
git commit -m "docs(dashboard): devlog + CLAUDE.md §5 + TECH_DEBT"
git push -u origin feat/dashboard-overview
```

Создать PR в `main` (заголовок «feat: дашборд «Обзор» (начальный экран, фаза 1)»), в теле — ссылки на спеку/план, чек-лист развилок O1–O6, отметка «read-only, действия инертны».

---

## Self-Review (выполнено при написании плана)

- **Spec coverage:** метрики Позиции/Издания/Вендоры → Task 2/5/10; черновики → Task 2/5/10; «Требует внимания» (кандидаты+залежавшиеся, «всё чисто») → Task 4/5/7/10; детерминизм последнего релиза → Task 2; бренд-ключ → Task 2; is_stale из конфига → Task 3/5; детект→null → Task 4/5; токен warning → Task 1; skeleton → Task 6; адаптив → Task 10; роут / → Task 9; success отложен → Task 11 TECH_DEBT. Покрыто.
- **Placeholder scan:** заглушка `DashboardScreen` в Task 9 — намеренная, заменяется в Task 10 (не placeholder-в-проде). Прочих нет.
- **Type consistency:** `count_merge_candidates`, `normalize_vendor_name`, `Dashboard/DashboardSummary/DashboardDraft`, `useDashboard`, `formatRelative`/`hasAttention`, `dashboardFixture` — имена согласованы между тасками.
