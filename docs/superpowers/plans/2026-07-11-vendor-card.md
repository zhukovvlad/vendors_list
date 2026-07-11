# Карточка вендора + кликабельные вендоры в каталоге — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Экран карточки вендора (`/vendors/$vendorId`) с блоками идентичности,
соглашения-тумблера, alias'ов, объединения и обратного индекса «Где разрешён» с
исключениями по правилу «граница — релиз»; плюс кликабельные вендор-теги в матрице.

**Architecture:** Правило исключения — одной истиной в SQL (set-returning функция
`vendor_where_allowed`, новая Alembic-ревизия чистым SQL). Роутер `vendors` читает
готовые строки и вкладывает в дерево (презентация, не логика); мутации (тумблер
соглашения, alias CRUD) — через `Depends(tx)`, аудит соглашения делает существующий
триггер БД. Фронт — экран на TanStack Query/Router поверх сгенерированных типов.

**Tech Stack:** PostgreSQL 18 (SQLAlchemy Core async, Alembic чистым SQL), FastAPI +
Pydantic v2, Vite + React + TS, shadcn/ui + Tailwind, TanStack Router/Query, vitest + MSW.

Спека: [docs/superpowers/specs/2026-07-11-vendor-card-design.md](../specs/2026-07-11-vendor-card-design.md).

## Global Constraints

Каждая задача неявно наследует эти правила (CLAUDE.md «Золотые правила»):

- **Schema-first, без ORM.** Только SQLAlchemy Core (`text(...)`); ORM запрещён.
- **Не дублировать вычислимое.** Правило исключения — в SQL-функции; API читает готовое.
- **Пишущие эндпоинты — только через `Depends(tx)`** (ставит `set_config('app.user', …, is_local=true)` bind-параметром). Читающие — `dependencies=[Depends(require_user)]` + `Depends(read_conn)`.
- **Роли — в API:** `viewer` читает; правки — `Depends(require_admin)`.
- **Базовые `0001/0002` неизменны.** Новые изменения — новой ревизией чистым SQL (`op.execute`).
- **UI только на русском.** Локализация значений enum — на фронте.
- **`main` зелёный:** ветка `feat/vendor-card` (уже создана), `just ci` зелёный на каждом слайсе, мерж через PR.
- **Типы сквозные:** после правок бэкенд-контракта — `just types` (регенерит `frontend/src/api/schema.d.ts`).
- **db-тесты (маркер `db`)** идут на тест-ветке Neon; изоляция — откат транзакции. Новую ревизию накатить на тест-ветку: `just migrate-test` (иначе функции нет — тесты упадут).

---

## Файловая структура

**Создать:**
- `backend/migrations/versions/0005_vendor_where_allowed.py` — функция правила исключения.
- `backend/app/routers/vendors.py` — роутер карточки (чтение + мутации).
- `backend/tests/db/test_vendor_where_allowed.py` — db-тесты правила.
- `backend/tests/api/test_vendors.py` — api-тесты чтения, мутаций, RBAC.
- `frontend/src/screens/vendors/VendorCardScreen.tsx` — экран карточки.
- `frontend/src/screens/vendors/model.ts` — чистые хелперы (локализация, тексты).
- `frontend/src/screens/vendors/model.test.ts` — юниты хелперов.
- `frontend/src/screens/vendors/VendorCardScreen.test.tsx` — тесты экрана.
- `frontend/src/components/ui/switch.tsx` + `switch.test.tsx` — DS-примитив (через shadcn).
- `frontend/src/components/ui/accordion.tsx` + `accordion.test.tsx` — DS-примитив (через shadcn).

**Изменить:**
- `backend/tests/factories.py` — расширить `make_release_listing`; добавить `make_alias`.
- `backend/app/schemas/__init__.py` — схемы карточки/мутаций.
- `backend/app/routers/__init__.py` — зарегистрировать `vendors`.
- `frontend/src/router.tsx` — динамический роут `/vendors/$vendorId`.
- `frontend/src/api/queries.ts` — хуки чтения + мутаций.
- `frontend/src/screens/matrix/columns.tsx` — обернуть вендор-тег в `Link`.
- `frontend/src/screens/matrix/MatrixScreen.test.tsx` — тест навигации по клику.
- `frontend/src/test/msw/handlers.ts` — MSW-хендлеры вендора.
- `CLAUDE.md` §5 + карта репо; `docs/TECH_DEBT.md`; `docs/devlog/2026-07-11-vendor-card.md`.

---

## Task 1: SQL-функция `vendor_where_allowed` + db-тесты правила

**Files:**
- Create: `backend/migrations/versions/0005_vendor_where_allowed.py`
- Modify: `backend/tests/factories.py`
- Test: `backend/tests/db/test_vendor_where_allowed.py`

**Interfaces:**
- Produces: SQL-функция `vendor_where_allowed(p_vendor_id int) RETURNS TABLE(building_type_id int, building_type_name text, position_id int, position_name text, segment_id int, segment_name text, state text, release_label text)`. `state` ∈ `'allowed' | 'excluded'`; строки упорядочены `building_type.sort_order → category_sort_path → position → segment`.
- Produces: `factories.make_release_listing(conn, release_id, position_id, segment_id=None, vendor_id=None, status='allowed')`, `factories.make_alias(conn, vendor_id, alias)`.

- [ ] **Step 0: Пре-флайт — сверить колонку `building_type.sort_order` по DDL**

Функция сортирует `ORDER BY bt.sort_order` (Step 4). Убедиться, что колонка есть, до применения миграции:

Run: `grep -n "sort_order" backend/migrations/sql/0001_core_schema.sql` (или Grep по `CREATE TABLE building_type`).
Expected: в блоке `CREATE TABLE building_type (…)` присутствует `sort_order int NOT NULL DEFAULT 0` (сверено — [0001:37-42](../../../backend/migrations/sql/0001_core_schema.sql#L37)). Тогда `bt.sort_order` в Step 4 оставить как есть.
Если бы колонки не было (не наш случай) — заменить `bt.sort_order` на `bt.id` в `ORDER BY` тела функции.

- [ ] **Step 1: Расширить фабрику `make_release_listing` и добавить `make_alias`**

В `backend/tests/factories.py` заменить `make_release_listing` (сейчас принимает только `release_id`/`position_id`/`status`) на вариант с `segment_id`/`vendor_id` (старые вызовы из dashboard-тестов остаются валидны — новые параметры опциональны):

```python
async def make_release_listing(
    conn: AsyncConnection,
    release_id: int,
    position_id: int,
    segment_id: int | None = None,
    vendor_id: int | None = None,
    status: str = "allowed",
) -> int:
    """Минимальная строка снимка издания (release_listing без триггеров)."""
    return (
        await conn.execute(
            text(
                "INSERT INTO release_listing "
                "(release_id, position_id, segment_id, vendor_id, status) "
                "VALUES (:r, :p, :s, :v, :st) RETURNING id"
            ),
            {"r": release_id, "p": position_id, "s": segment_id, "v": vendor_id, "st": status},
        )
    ).scalar_one()


async def make_alias(conn: AsyncConnection, vendor_id: int, alias: str) -> int:
    return (
        await conn.execute(
            text("INSERT INTO vendor_alias (vendor_id, alias) VALUES (:v, :a) RETURNING id"),
            {"v": vendor_id, "a": alias},
        )
    ).scalar_one()
```

- [ ] **Step 2: Написать падающие db-тесты правила**

Create `backend/tests/db/test_vendor_where_allowed.py`:

```python
"""vendor_where_allowed: правило исключения (граница легитимности — релиз).

4 кейса ТЗ + детерминизм последнего релиза + порядок позиций. Изоляция —
свежий building_type на каждый тест (функция глобальна, но фильтр по вендору
и свежему типу делает результат детерминированным)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _rows(db_conn, vendor_id: int) -> list[dict]:
    return (
        await db_conn.execute(
            text("SELECT * FROM vendor_where_allowed(:v)"), {"v": vendor_id}
        )
    ).mappings().all()


async def test_allowed_when_live_and_released(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-a")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-a-seg")
    cat = await f.make_category(db_conn, name="wa-a-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-a-pos")
    v = await f.make_vendor(db_conn, name="wa-a-v")
    rid = await f.make_release(db_conn, building_type_id=bt, status="published")
    await f.make_release_listing(db_conn, release_id=rid, position_id=pos, segment_id=seg, vendor_id=v)
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["state"] == "allowed"
    assert rows[0]["release_label"] is None


async def test_excluded_when_released_but_not_live(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-b")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-b-seg")
    cat = await f.make_category(db_conn, name="wa-b-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-b-pos")
    v = await f.make_vendor(db_conn, name="wa-b-v")
    rid = await f.make_release(db_conn, building_type_id=bt, label="ред. B", status="published")
    await f.make_release_listing(db_conn, release_id=rid, position_id=pos, segment_id=seg, vendor_id=v)
    # живой строки НЕ создаём → был в релизе, сейчас исключён
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["state"] == "excluded"
    assert rows[0]["release_label"] == "ред. B"


async def test_draft_only_typo_not_shown(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-c")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-c-seg")
    cat = await f.make_category(db_conn, name="wa-c-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-c-pos")
    v = await f.make_vendor(db_conn, name="wa-c-v")
    # добавлен в живой и мягко удалён; в релиз не попадал
    lid = await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")
    await db_conn.execute(text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid})
    assert await _rows(db_conn, v) == []


async def test_never_anywhere_not_shown(db_conn) -> None:
    v = await f.make_vendor(db_conn, name="wa-d-v")
    assert await _rows(db_conn, v) == []


async def test_excluded_label_from_latest_release_on_equal_dates(db_conn) -> None:
    # два published с равной датой; label берётся у победителя (больший id)
    bt = await f.make_building_type(db_conn, code="wa-det")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-det-seg")
    cat = await f.make_category(db_conn, name="wa-det-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-det-pos")
    v = await f.make_vendor(db_conn, name="wa-det-v")
    r1 = await f.make_release(db_conn, building_type_id=bt, label="старый", status="published")
    r2 = await f.make_release(db_conn, building_type_id=bt, label="новый", status="published")
    await db_conn.execute(
        text("UPDATE release SET effective_date = DATE '2026-01-01' WHERE id IN (:a, :b)"),
        {"a": r1, "b": r2},
    )
    await f.make_release_listing(db_conn, release_id=r1, position_id=pos, segment_id=seg, vendor_id=v)
    await f.make_release_listing(db_conn, release_id=r2, position_id=pos, segment_id=seg, vendor_id=v)
    rows = await _rows(db_conn, v)
    assert len(rows) == 1
    assert rows[0]["release_label"] == "новый"  # r2.id > r1.id


async def test_positions_ordered_by_category_sort_path(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-ord")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="wa-ord-seg")
    # два раздела с разным sort_order → порядок позиций следует за деревом
    cat_b = await db_conn.execute(
        text("INSERT INTO category (name, sort_order) VALUES ('wa-ord-B', 2) RETURNING id")
    )
    cat_b_id = cat_b.scalar_one()
    cat_a = await db_conn.execute(
        text("INSERT INTO category (name, sort_order) VALUES ('wa-ord-A', 1) RETURNING id")
    )
    cat_a_id = cat_a.scalar_one()
    v = await f.make_vendor(db_conn, name="wa-ord-v")
    pos_b = await f.make_position(db_conn, category_id=cat_b_id, name="Б-позиция")
    pos_a = await f.make_position(db_conn, category_id=cat_a_id, name="А-позиция")
    await f.make_listing(db_conn, position_id=pos_b, segment_id=seg, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos_a, segment_id=seg, vendor_id=v, status="allowed")
    names = [r["position_name"] for r in await _rows(db_conn, v)]
    assert names == ["А-позиция", "Б-позиция"]  # sort_order 1 раньше 2
```

- [ ] **Step 3: Прогнать — убедиться, что падают (функции ещё нет)**

Run: `just migrate-test` (нечего накатывать — ревизии ещё нет), затем
`cd backend; uv run pytest tests/db/test_vendor_where_allowed.py -v`
Expected: FAIL — `function vendor_where_allowed(integer) does not exist`.

- [ ] **Step 4: Написать миграцию**

Create `backend/migrations/versions/0005_vendor_where_allowed.py`:

```python
"""Ревизия №5: функция vendor_where_allowed (обратный индекс «Где разрешён»).

Правило исключения (граница легитимности — релиз): вендор показывается по классу
как allowed, если жива строка listing со status='allowed'; как excluded — если он
был в снимке последнего published-релиза этого типа объекта, но живой строки нет.
Черновичные опечатки (не в релизе, добавлен и удалён) и «нигде не было» — не в
выборке. brand-key НЕ разворачиваем (фильтр строго по vendor_id).

Revision ID: 0005_vendor_where_allowed
Revises: 0004_dashboard_views
"""

from __future__ import annotations

from alembic import op

revision = "0005_vendor_where_allowed"
down_revision = "0004_dashboard_views"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION vendor_where_allowed(p_vendor_id int)
RETURNS TABLE (
    building_type_id   int,
    building_type_name text,
    position_id        int,
    position_name      text,
    segment_id         int,
    segment_name       text,
    state              text,
    release_label      text
) LANGUAGE sql STABLE AS
$fn$
WITH current_release AS (          -- последний published-релиз на каждый тип
    SELECT DISTINCT ON (building_type_id) id, building_type_id, label
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC
),
released AS (                      -- вендор в снимке этого релиза (allowed)
    SELECT DISTINCT cr.building_type_id, rl.position_id, rl.segment_id, cr.label
    FROM current_release cr
    JOIN release_listing rl ON rl.release_id = cr.id
    WHERE rl.vendor_id = p_vendor_id AND rl.status = 'allowed'
      AND rl.position_id IS NOT NULL AND rl.segment_id IS NOT NULL
),
live AS (                          -- вендор жив сейчас (allowed)
    SELECT seg.building_type_id, l.position_id, l.segment_id
    FROM listing l
    JOIN segment seg ON seg.id = l.segment_id
    WHERE l.vendor_id = p_vendor_id AND l.status = 'allowed'
      AND l.deleted_at IS NULL
),
keys AS (
    SELECT building_type_id, position_id, segment_id FROM live
    UNION
    SELECT building_type_id, position_id, segment_id FROM released
)
SELECT bt.id, bt.name, pos.id, pos.name, seg.id, seg.name,
       CASE WHEN lv.position_id IS NOT NULL THEN 'allowed' ELSE 'excluded' END,
       CASE WHEN lv.position_id IS NULL THEN rl.label ELSE NULL END
FROM keys k
JOIN building_type bt ON bt.id  = k.building_type_id
JOIN position      pos ON pos.id = k.position_id
JOIN segment       seg ON seg.id = k.segment_id
LEFT JOIN live     lv ON (lv.building_type_id, lv.position_id, lv.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
LEFT JOIN released rl ON (rl.building_type_id, rl.position_id, rl.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
ORDER BY bt.sort_order,
         category_sort_path(pos.category_id), pos.sort_order, pos.name,
         seg.sort_order, seg.name;
$fn$;
"""

_DOWN = "DROP FUNCTION IF EXISTS vendor_where_allowed(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
```

> Тело функции обёрнуто в `$fn$…$fn$` (не `$$`), потому что весь `_UP` — тоже
> строка; вложенный `$$` закрыл бы её преждевременно.

- [ ] **Step 5: Накатить на тест-ветку и прогнать тесты**

Run: `just migrate-test` — Expected: применяет `0005_vendor_where_allowed`.
Run: `cd backend; uv run pytest tests/db/test_vendor_where_allowed.py -v`
Expected: PASS (6 тестов). Также прогнать `uv run pytest tests/db/test_dashboard_views.py -v` — Expected: PASS (расширение фабрики обратно совместимо).

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0005_vendor_where_allowed.py backend/tests/factories.py backend/tests/db/test_vendor_where_allowed.py
git commit -m "feat(db): функция vendor_where_allowed (правило исключения «Где разрешён»)"
```

---

## Task 2: Схемы + роутер `vendors`, эндпоинт `GET /vendors/{vendor_id}`

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/routers/vendors.py`
- Modify: `backend/app/routers/__init__.py`
- Test: `backend/tests/api/test_vendors.py`

**Interfaces:**
- Consumes: `factories` из Task 1; `conftest` фикстуры `client`/`as_admin`/`as_viewer`/`db_conn`.
- Produces: `GET /vendors/{vendor_id} -> VendorCard`; Pydantic `VendorCard`, `VendorAlias`, `VendorRepresents`. Роутер `vendors.router` зарегистрирован.

- [ ] **Step 1: Добавить схемы чтения**

В конец `backend/app/schemas/__init__.py`:

```python
# --- Карточка вендора --------------------------------------------------------
class VendorAlias(BaseModel):
    model_config = _from_row
    id: int
    alias: str


class VendorRepresents(BaseModel):
    model_config = _from_row
    id: int
    name: str


class VendorCard(BaseModel):
    id: int
    name: str
    kind: str
    note: str | None
    starred: bool
    represents: VendorRepresents | None
    represented_count: int
    aliases: list[VendorAlias]
```

- [ ] **Step 2: Написать падающий api-тест чтения шапки**

Create `backend/tests/api/test_vendors.py`:

```python
"""Карточка вендора: чтение шапки/дерева, мутации, RBAC."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_get_vendor_header(client, as_viewer, db_conn) -> None:
    owner = await f.make_vendor(db_conn, name="Owner-Co", kind="manufacturer")
    v = await f.make_vendor(db_conn, name="Sub-Co", kind="supplier", represents_id=owner)
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    await f.make_alias(db_conn, vendor_id=v, alias="SubCo")
    await f.make_vendor(db_conn, name="Sub-Co-2", represents_id=v)  # обратная ссылка на v

    resp = await client.get(f"/vendors/{v}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Sub-Co"
    assert body["kind"] == "supplier"
    assert body["starred"] is True
    assert body["represents"]["name"] == "Owner-Co"
    assert body["represented_count"] == 1
    assert [a["alias"] for a in body["aliases"]] == ["SubCo"]


async def test_get_vendor_404(client, as_viewer) -> None:
    resp = await client.get("/vendors/999999")
    assert resp.status_code == 404
```

- [ ] **Step 3: Прогнать — падает (роутера нет → 404 на существующем/ошибка)**

Run: `cd backend; uv run pytest tests/api/test_vendors.py::test_get_vendor_header -v`
Expected: FAIL (маршрут не зарегистрирован — 404 на реальном вендоре).

- [ ] **Step 4: Написать роутер (чтение шапки)**

Create `backend/app/routers/vendors.py`:

```python
"""Карточка вендора. Чтение — из готовых таблиц/функций БД; мутации — через tx.

«Где разрешён» приходит из функции vendor_where_allowed (правило исключения в БД);
роутер только вкладывает плоские строки в дерево (презентация, не логика).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..auth import require_user
from ..db import read_conn
from ..schemas import VendorAlias, VendorCard, VendorRepresents

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("/{vendor_id}", response_model=VendorCard, dependencies=[Depends(require_user)])
async def get_vendor(vendor_id: int, conn: AsyncConnection = Depends(read_conn)) -> VendorCard:
    row = (
        await conn.execute(
            text("SELECT id, name, kind, represents_id, note FROM vendor WHERE id = :id"),
            {"id": vendor_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")

    starred = (
        await conn.execute(text("SELECT vendor_starred(:id)"), {"id": vendor_id})
    ).scalar_one()
    represented_count = (
        await conn.execute(
            text("SELECT count(*) FROM vendor WHERE represents_id = :id"), {"id": vendor_id}
        )
    ).scalar_one()

    represents = None
    if row["represents_id"] is not None:
        owner = (
            await conn.execute(
                text("SELECT id, name FROM vendor WHERE id = :id"), {"id": row["represents_id"]}
            )
        ).mappings().one()
        represents = VendorRepresents.model_validate(dict(owner))

    aliases = [
        VendorAlias.model_validate(dict(a))
        for a in (
            await conn.execute(
                text("SELECT id, alias FROM vendor_alias WHERE vendor_id = :id ORDER BY alias"),
                {"id": vendor_id},
            )
        ).mappings()
    ]

    return VendorCard(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        note=row["note"],
        starred=starred,
        represents=represents,
        represented_count=represented_count,
        aliases=aliases,
    )
```

- [ ] **Step 5: Зарегистрировать роутер**

В `backend/app/routers/__init__.py`:

```python
"""API-роутеры. Читают из готовых вьюх/таблиц БД; расчёты не дублируют."""

from . import compliance, dashboard, listings, meta, releases, vendors

__all__ = ["compliance", "dashboard", "listings", "meta", "releases", "vendors"]
```

- [ ] **Step 6: Прогнать — PASS**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -v`
Expected: PASS (`test_get_vendor_header`, `test_get_vendor_404`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/app/routers/__init__.py backend/tests/api/test_vendors.py
git commit -m "feat(api): GET /vendors/{id} — шапка карточки (имя/тип/соглашение/бренд/aliases)"
```

---

## Task 3: Эндпоинт `GET /vendors/{vendor_id}/where-allowed` + `just types`

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/vendors.py`
- Test: `backend/tests/api/test_vendors.py`

**Interfaces:**
- Consumes: функция `vendor_where_allowed` (Task 1); роутер `vendors` (Task 2).
- Produces: `GET /vendors/{vendor_id}/where-allowed -> WhereAllowed`; схемы `WhereAllowed`, `WhereAllowedStandard`, `WhereAllowedPosition`, `WhereAllowedChip`.

- [ ] **Step 1: Добавить схемы дерева**

В `backend/app/schemas/__init__.py` (после `VendorCard`):

```python
class WhereAllowedChip(BaseModel):
    segment_id: int
    segment_name: str
    state: str                    # 'allowed' | 'excluded'
    release_label: str | None     # для 'excluded' — тултип


class WhereAllowedPosition(BaseModel):
    position_id: int
    position_name: str
    chips: list[WhereAllowedChip]


class WhereAllowedStandard(BaseModel):
    building_type_id: int
    building_type_name: str
    position_count: int
    positions: list[WhereAllowedPosition]


class WhereAllowed(BaseModel):
    standards: list[WhereAllowedStandard]
```

- [ ] **Step 2: Написать падающий api-тест дерева**

Добавить в `backend/tests/api/test_vendors.py`:

```python
async def test_where_allowed_tree(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-api")
    seg1 = await f.make_segment(db_conn, building_type_id=bt, name="Класс-1", sort_order=1)
    seg2 = await f.make_segment(db_conn, building_type_id=bt, name="Класс-2", sort_order=2)
    cat = await f.make_category(db_conn, name="wa-api-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-api-pos")
    v = await f.make_vendor(db_conn, name="wa-api-v")
    rid = await f.make_release(db_conn, building_type_id=bt, label="ред. API", status="published")
    # seg1 — жив (allowed); seg2 — был в релизе, живого нет (excluded)
    await f.make_release_listing(db_conn, release_id=rid, position_id=pos, segment_id=seg1, vendor_id=v)
    await f.make_release_listing(db_conn, release_id=rid, position_id=pos, segment_id=seg2, vendor_id=v)
    await f.make_listing(db_conn, position_id=pos, segment_id=seg1, vendor_id=v, status="allowed")

    resp = await client.get(f"/vendors/{v}/where-allowed")
    assert resp.status_code == 200
    standards = resp.json()["standards"]
    std = next(s for s in standards if s["building_type_id"] == bt)
    assert std["position_count"] == 1
    chips = {c["segment_name"]: c for c in std["positions"][0]["chips"]}
    assert chips["Класс-1"]["state"] == "allowed"
    assert chips["Класс-2"]["state"] == "excluded"
    assert chips["Класс-2"]["release_label"] == "ред. API"
```

- [ ] **Step 3: Прогнать — падает (маршрута нет)**

Run: `cd backend; uv run pytest tests/api/test_vendors.py::test_where_allowed_tree -v`
Expected: FAIL (404).

- [ ] **Step 4: Реализовать эндпоинт (вложение плоских строк)**

В `backend/app/routers/vendors.py` добавить импорты и эндпоинт:

```python
from ..schemas import (
    VendorAlias,
    VendorCard,
    VendorRepresents,
    WhereAllowed,
    WhereAllowedChip,
    WhereAllowedPosition,
    WhereAllowedStandard,
)


@router.get(
    "/{vendor_id}/where-allowed",
    response_model=WhereAllowed,
    dependencies=[Depends(require_user)],
)
async def get_where_allowed(
    vendor_id: int, conn: AsyncConnection = Depends(read_conn)
) -> WhereAllowed:
    rows = (
        await conn.execute(
            text("SELECT * FROM vendor_where_allowed(:v)"), {"v": vendor_id}
        )
    ).mappings().all()

    # Строки уже упорядочены (тип → позиция → класс) — группируем последовательно.
    standards: list[WhereAllowedStandard] = []
    for r in rows:
        if not standards or standards[-1].building_type_id != r["building_type_id"]:
            standards.append(
                WhereAllowedStandard(
                    building_type_id=r["building_type_id"],
                    building_type_name=r["building_type_name"],
                    position_count=0,
                    positions=[],
                )
            )
        std = standards[-1]
        if not std.positions or std.positions[-1].position_id != r["position_id"]:
            std.positions.append(
                WhereAllowedPosition(
                    position_id=r["position_id"],
                    position_name=r["position_name"],
                    chips=[],
                )
            )
            std.position_count += 1
        std.positions[-1].chips.append(
            WhereAllowedChip(
                segment_id=r["segment_id"],
                segment_name=r["segment_name"],
                state=r["state"],
                release_label=r["release_label"],
            )
        )

    return WhereAllowed(standards=standards)
```

- [ ] **Step 5: Прогнать — PASS**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -v`
Expected: PASS (все тесты вендора).

- [ ] **Step 6: Регенерировать TS-типы**

Run: `just types`
Expected: `frontend/src/api/schema.d.ts` содержит `/vendors/{vendor_id}` и `/vendors/{vendor_id}/where-allowed`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/tests/api/test_vendors.py frontend/src/api/schema.d.ts
git commit -m "feat(api): GET /vendors/{id}/where-allowed — дерево «Где разрешён» + типы"
```

> **Note:** `schema.d.ts` gitignored (CLAUDE.md). Если `git add` его игнорит — это ок, он регенерится в CI; коммить остальное.

---

## Task 4: Роут `/vendors/$vendorId`, хук `useVendor`, шапка карточки + DS `switch`

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/api/queries.ts`
- Create: `frontend/src/screens/vendors/model.ts`, `model.test.ts`
- Create: `frontend/src/screens/vendors/VendorCardScreen.tsx`, `VendorCardScreen.test.tsx`
- Create: `frontend/src/components/ui/switch.tsx`, `switch.test.tsx` (через shadcn)
- Modify: `frontend/src/test/msw/handlers.ts`

**Interfaces:**
- Consumes: `GET /vendors/{vendor_id}` (Task 2/3), типы из `schema.d.ts`.
- Produces: `vendorCardRoute` (экспорт), `useVendor(id)`, `kindLabel(kind)`, `VendorCardScreen`.

- [ ] **Step 1: Добавить DS-примитив `switch`**

Run: `cd frontend; npx --yes shadcn@latest add switch`
Expected: создан `frontend/src/components/ui/switch.tsx` (radix + токены).

Create `frontend/src/components/ui/switch.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Switch } from "./switch"

describe("Switch", () => {
  it("рендерит роль switch и отражает checked", () => {
    render(<Switch checked readOnly aria-label="тест" />)
    expect(screen.getByRole("switch")).toBeChecked()
  })
})
```

- [ ] **Step 2: Хелперы `model.ts` + падающие юниты**

Create `frontend/src/screens/vendors/model.ts`:

```ts
/** Чистые хелперы карточки вендора: локализация enum и тексты (без версий релиза). */

const KIND_LABELS: Record<string, string> = {
  manufacturer: "производитель",
  supplier: "поставщик",
  other: "прочее",
}

/** Локализованное имя типа вендора; неизвестное значение — как есть. */
export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind
}

/** Тултип зачёркнутого чипа: релиз идентифицируется label, не номером версии. */
export function excludedTooltip(releaseLabel: string | null): string {
  return releaseLabel
    ? `Был в релизе «${releaseLabel}», исключён в текущем черновике`
    : "Был в последнем релизе, исключён в текущем черновике"
}

export const WHERE_ALLOWED_LEGEND =
  "зачёркнутый класс — был в последнем релизе, исключён · показано текущее состояние стандартов"
```

Create `frontend/src/screens/vendors/model.test.ts`:

```ts
import { describe, expect, it } from "vitest"

import { excludedTooltip, kindLabel } from "./model"

describe("kindLabel", () => {
  it("локализует известные типы", () => {
    expect(kindLabel("manufacturer")).toBe("производитель")
    expect(kindLabel("supplier")).toBe("поставщик")
    expect(kindLabel("other")).toBe("прочее")
  })
  it("неизвестное значение отдаёт как есть", () => {
    expect(kindLabel("weird")).toBe("weird")
  })
})

describe("excludedTooltip", () => {
  it("вставляет label релиза", () => {
    expect(excludedTooltip("ред. 25.03")).toContain("«ред. 25.03»")
  })
  it("без label — обобщённо", () => {
    expect(excludedTooltip(null)).toBe(
      "Был в последнем релизе, исключён в текущем черновике"
    )
  })
})
```

Run: `cd frontend; npm run test -- model.test` — Expected: PASS (чистые функции).

- [ ] **Step 3: Хук `useVendor`**

В `frontend/src/api/queries.ts` добавить:

```ts
export function useVendor(id: number) {
  return useQuery({
    queryKey: ["vendor", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/vendors/{vendor_id}", {
        params: { path: { vendor_id: id } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /vendors/{id}")
      return data
    },
  })
}
```

- [ ] **Step 4: MSW-хендлеры вендора**

В `frontend/src/test/msw/handlers.ts` добавить фикстуру и хендлеры:

```ts
export const vendorFixture = {
  id: 5,
  name: "System Air",
  kind: "manufacturer",
  note: null as string | null,
  starred: true,
  represents: null as { id: number; name: string } | null,
  represented_count: 0,
  aliases: [
    { id: 1, alias: "System Air" },
    { id: 2, alias: "SystemAir" },
  ],
}

export const whereAllowedFixture = {
  standards: [
    {
      building_type_id: 1,
      building_type_name: "Жилой дом",
      position_count: 1,
      positions: [
        {
          position_id: 100,
          position_name: "Радиаторы отопления",
          chips: [
            { segment_id: 11, segment_name: "Делюкс", state: "allowed", release_label: null },
            { segment_id: 14, segment_name: "Бизнес", state: "excluded", release_label: "ред. 25.03.2026" },
          ],
        },
      ],
    },
  ],
}
```

И в массив `handlers`:

```ts
  http.get(`${BASE}/vendors/:vendorId`, () => HttpResponse.json(vendorFixture)),
  http.get(`${BASE}/vendors/:vendorId/where-allowed`, () =>
    HttpResponse.json(whereAllowedFixture)
  ),
```

> Порядок: хендлер `:vendorId/where-allowed` должен идти ПОСЛЕ `:vendorId` только если бы они конфликтовали — MSW матчит по полному пути, конфликта нет; порядок безразличен.

- [ ] **Step 5: Роут `/vendors/$vendorId`**

В `frontend/src/router.tsx`: импорт экрана + новый роут + добавить в `routeTree`:

```tsx
import { VendorCardScreen } from "@/screens/vendors/VendorCardScreen"
```

```tsx
// Экспортируем: экран берёт vendorCardRoute.useParams() (строгий резолв на том же
// route-инстансе, что и дерево тестов).
export const vendorCardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/vendors/$vendorId",
  component: VendorCardScreen,
})
```

```tsx
export const routeTree = rootRoute.addChildren([
  dashboardRoute,
  matrixRoute,
  designSystemRoute,
  vendorsRoute,
  vendorCardRoute,
])
```

- [ ] **Step 6: Падающий тест шапки**

Create `frontend/src/screens/vendors/VendorCardScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { render, screen } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { routeTree } from "@/router"
import { server } from "@/test/msw/server"
import { vendorFixture } from "@/test/msw/handlers"

function renderAt(path = "/vendors/5") {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>
  )
}

describe("VendorCardScreen — шапка", () => {
  it("рисует имя, локализованный тип, пилюлю соглашения и статус бренда", async () => {
    renderAt()
    expect(await screen.findByText("System Air")).toBeInTheDocument()
    expect(screen.getByText("производитель")).toBeInTheDocument()
    expect(screen.getByText("соглашение")).toBeInTheDocument()
    expect(screen.getByText("самостоятельный бренд")).toBeInTheDocument()
  })

  it("показывает alias'ы", async () => {
    renderAt()
    expect(await screen.findByText("SystemAir")).toBeInTheDocument()
  })

  it("скрывает заметку, когда она пустая", async () => {
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, note: null })
      )
    )
    renderAt()
    await screen.findByText("System Air")
    expect(screen.queryByTestId("vendor-note")).not.toBeInTheDocument()
  })

  it("пилюля соглашения скрыта при starred=false", async () => {
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, starred: false })
      )
    )
    renderAt()
    await screen.findByText("System Air")
    expect(screen.queryByText("соглашение")).not.toBeInTheDocument()
  })
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (экрана нет).

- [ ] **Step 7: Реализовать шапку экрана**

Create `frontend/src/screens/vendors/VendorCardScreen.tsx`:

```tsx
import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"

import { useVendor } from "@/api/queries"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import { kindLabel } from "./model"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)

  if (isPending)
    return <div className="py-16 text-center text-muted-foreground">Загрузка…</div>
  if (isError || !data)
    return <div className="py-16 text-center text-muted-foreground">Вендор не найден</div>

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-h3 font-medium">{data.name}</h1>
          <Badge variant="outline">{kindLabel(data.kind)}</Badge>
          {data.starred && (
            <Badge variant="outline" className="gap-1">
              <Star className="size-3 fill-current" aria-hidden />
              соглашение
            </Badge>
          )}
          <span className="flex-1" />
          <label className="flex items-center gap-2 text-small">
            Соглашение
            <Switch
              checked={data.starred}
              disabled
              aria-label="Соглашение о сотрудничестве"
            />
          </label>
        </div>
        <div className="text-small text-muted-foreground">
          {data.represents ? (
            <>
              представляет:{" "}
              <Link
                to="/vendors/$vendorId"
                params={{ vendorId: String(data.represents.id) }}
                className="underline"
              >
                {data.represents.name}
              </Link>
            </>
          ) : (
            "самостоятельный бренд"
          )}
        </div>
      </header>

      {data.note && (
        <p data-testid="vendor-note" className="text-small">
          {data.note}
        </p>
      )}

      <section className="space-y-2">
        <div className="text-caption uppercase text-muted-foreground">
          Варианты написания
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">—</span>
          )}
          {data.aliases.map((a) => (
            <Badge key={a.id} variant="outline">
              {a.alias}
            </Badge>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-caption uppercase text-muted-foreground">
          Бренд и объединение
        </div>
        {data.represented_count > 0 && (
          <div className="text-small text-muted-foreground">
            {data.represented_count} брендов представлены этим
          </div>
        )}
        <Button variant="outline" disabled title="в разработке">
          Объединить
        </Button>
      </section>
    </div>
  )
}
```

- [ ] **Step 8: Прогнать фронт-тесты + typecheck**

Run: `cd frontend; npm run test -- VendorCardScreen switch model.test`
Expected: PASS.
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/router.tsx frontend/src/api/queries.ts frontend/src/screens/vendors/ frontend/src/components/ui/switch.tsx frontend/src/components/ui/switch.test.tsx frontend/src/test/msw/handlers.ts
git commit -m "feat(vendors): экран карточки — шапка/note/aliases/бренд + роут /vendors/\$vendorId"
```

---

## Task 5: Блок «Где разрешён» (аккордеон, чипы, зачёркивание, легенда) + DS `accordion`

**Files:**
- Create: `frontend/src/components/ui/accordion.tsx`, `accordion.test.tsx` (через shadcn)
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`, `VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: `GET /vendors/{vendor_id}/where-allowed` (Task 3), `whereAllowedFixture` (Task 4), `excludedTooltip`/`WHERE_ALLOWED_LEGEND` (Task 4).
- Produces: `useVendorWhereAllowed(id)`; блок «Где разрешён» в экране.

- [ ] **Step 1: Добавить DS-примитив `accordion`**

Run: `cd frontend; npx --yes shadcn@latest add accordion`
Expected: создан `frontend/src/components/ui/accordion.tsx`.

Create `frontend/src/components/ui/accordion.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "./accordion"

describe("Accordion", () => {
  it("раскрывает контент по клику на триггер", async () => {
    render(
      <Accordion type="single" collapsible>
        <AccordionItem value="a">
          <AccordionTrigger>Заголовок</AccordionTrigger>
          <AccordionContent>Тело</AccordionContent>
        </AccordionItem>
      </Accordion>
    )
    await userEvent.click(screen.getByText("Заголовок"))
    expect(await screen.findByText("Тело")).toBeVisible()
  })
})
```

- [ ] **Step 2: Хук `useVendorWhereAllowed`**

В `frontend/src/api/queries.ts`:

```ts
export function useVendorWhereAllowed(id: number) {
  return useQuery({
    queryKey: ["vendor-where-allowed", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/vendors/{vendor_id}/where-allowed", {
        params: { path: { vendor_id: id } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /vendors/{id}/where-allowed")
      return data
    },
  })
}
```

- [ ] **Step 3: Падающий тест блока «Где разрешён»**

Добавить в `frontend/src/screens/vendors/VendorCardScreen.test.tsx`:

```tsx
import userEvent from "@testing-library/user-event"

describe("VendorCardScreen — Где разрешён", () => {
  it("раскрывает стандарт, показывает allowed-чип и зачёркнутый excluded с тултипом", async () => {
    renderAt()
    await screen.findByText("System Air")
    await userEvent.click(screen.getByText("Жилой дом"))
    expect(await screen.findByText("Делюкс")).toBeInTheDocument()
    const excluded = screen.getByText("Бизнес")
    // тултип/aria исключённого чипа несёт label релиза
    expect(excluded).toHaveAttribute(
      "aria-label",
      "Был в релизе «ред. 25.03.2026», исключён в текущем черновике"
    )
  })

  it("свёрнутый стандарт показывает счётчик позиций", async () => {
    renderAt()
    expect(await screen.findByText("1 позиций")).toBeInTheDocument()
  })
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (блока нет).

- [ ] **Step 4: Добавить блок «Где разрешён» в экран**

В `frontend/src/screens/vendors/VendorCardScreen.tsx` — импорты:

```tsx
import { useVendor, useVendorWhereAllowed } from "@/api/queries"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { excludedTooltip, kindLabel, WHERE_ALLOWED_LEGEND } from "./model"
```

В теле компонента после получения `data` добавить второй хук:

```tsx
  const whereAllowed = useVendorWhereAllowed(id)
```

И перед закрывающим `</div>` контейнера — секцию:

```tsx
      <section className="space-y-2">
        <div className="text-caption uppercase text-muted-foreground">Где разрешён</div>
        <Accordion type="multiple">
          {(whereAllowed.data?.standards ?? []).map((s) => (
            <AccordionItem key={s.building_type_id} value={String(s.building_type_id)}>
              <AccordionTrigger>
                <span className="flex-1 text-left">{s.building_type_name}</span>
                <span className="text-small text-muted-foreground">
                  {s.position_count} позиций
                </span>
              </AccordionTrigger>
              <AccordionContent className="space-y-3">
                {s.positions.map((p) => (
                  <div key={p.position_id} className="space-y-1.5">
                    <div className="text-small">{p.position_name}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {p.chips.map((c) =>
                        c.state === "allowed" ? (
                          <Badge key={c.segment_id} variant="outline">
                            {c.segment_name}
                          </Badge>
                        ) : (
                          <Badge
                            key={c.segment_id}
                            variant="outline"
                            className="border-dashed text-muted-foreground line-through"
                            title={excludedTooltip(c.release_label)}
                            aria-label={excludedTooltip(c.release_label)}
                          >
                            {c.segment_name}
                          </Badge>
                        )
                      )}
                    </div>
                  </div>
                ))}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
        <p className="text-caption text-muted-foreground">{WHERE_ALLOWED_LEGEND}</p>
      </section>
```

- [ ] **Step 5: Прогнать — PASS**

Run: `cd frontend; npm run test -- VendorCardScreen accordion`
Expected: PASS. Run: `cd frontend; npm run typecheck` — без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/accordion.tsx frontend/src/components/ui/accordion.test.tsx frontend/src/api/queries.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): блок «Где разрешён» — аккордеон/чипы/зачёркнутые исключения"
```

---

## Task 6: Кликабельные вендор-теги в матрице

**Files:**
- Modify: `frontend/src/screens/matrix/columns.tsx`
- Modify: `frontend/src/screens/matrix/MatrixScreen.test.tsx`

**Interfaces:**
- Consumes: `vendorCardRoute` (`/vendors/$vendorId`, Task 4); `vendor_id` уже в payload ячейки.
- Produces: клик по вендор-тегу → навигация на карточку.

- [ ] **Step 1: Падающий тест навигации**

Добавить в `frontend/src/screens/matrix/MatrixScreen.test.tsx` (внутри `describe("MatrixScreen"…)`):

```tsx
  it("клик по вендор-тегу ведёт на карточку /vendors/$id", async () => {
    const router = makeRouter()
    renderWith(router)
    await userEvent.click(await screen.findByText("Grundfos"))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/vendors/5")
    )
  })
```

> MSW-хендлер матрицы уже отдаёт `vendor_id: 5` для Grundfos; хендлер `/vendors/:vendorId` (Task 4) отвечает на переход. `routeTree` уже включает `vendorCardRoute`.

Run: `cd frontend; npm run test -- MatrixScreen` — Expected: FAIL (тег не ссылка).

- [ ] **Step 2: Обернуть тег в `Link`**

В `frontend/src/screens/matrix/columns.tsx` — импорт и правка `renderCell` (блок `cell.vendors.map`):

```tsx
import { Link } from "@tanstack/react-router"
```

```tsx
  if (cell.vendors.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {cell.vendors.map((v) => (
          <Link
            key={v.vendor_id}
            to="/vendors/$vendorId"
            params={{ vendorId: String(v.vendor_id) }}
            className="rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Badge
              variant="outline"
              title={v.note ?? undefined}
              className="cursor-pointer hover:border-foreground/40 hover:bg-accent"
            >
              {v.starred && (
                <Star
                  className="size-3 fill-current"
                  aria-label="действующее соглашение"
                />
              )}
              {v.name}
              {v.ujin_integration && (
                <span className="text-caption text-muted-foreground">Ujin</span>
              )}
            </Badge>
          </Link>
        ))}
      </div>
    )
  }
```

> Требования (`spec_text`) и прочерки (`—`) не трогаем — они остаются некликабельными.

- [ ] **Step 3: Прогнать — PASS**

Run: `cd frontend; npm run test -- MatrixScreen`
Expected: PASS (включая существующие тесты рендера/поиска/пагинации + новый навигационный).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/matrix/columns.tsx frontend/src/screens/matrix/MatrixScreen.test.tsx
git commit -m "feat(matrix): вендор-тег — ссылка на карточку /vendors/\$id (a11y: ссылка, не кнопка)"
```

---

## Task 7: Мутации бэкенда — тумблер соглашения + alias CRUD

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/vendors.py`
- Test: `backend/tests/api/test_vendors.py`

**Interfaces:**
- Consumes: роутер `vendors` (Task 2); фикстуры `client`/`as_admin`/`as_viewer`/`db_conn`.
- Produces: `PUT /vendors/{vendor_id}/agreement` (body `{active: bool}` → `{starred: bool}`); `POST /vendors/{vendor_id}/aliases` (body `{alias}` → `VendorAlias`, 409 при дубле); `DELETE /vendors/{vendor_id}/aliases/{alias_id}` (204). Схемы `AgreementToggle`, `AliasCreate`.

- [ ] **Step 1: Схемы запросов мутаций**

В `backend/app/schemas/__init__.py`:

```python
class AgreementToggle(BaseModel):
    active: bool


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1)
```

- [ ] **Step 2: Падающие api-тесты мутаций (механика O1 + RBAC)**

Добавить в `backend/tests/api/test_vendors.py`:

```python
async def _agreement_log_count(db_conn, vendor_id: int) -> int:
    return (
        await db_conn.execute(
            text(
                "SELECT count(*) FROM agreement_change_log "
                "WHERE agreement_id IN (SELECT id FROM agreement WHERE vendor_id = :v)"
            ),
            {"v": vendor_id},
        )
    ).scalar_one()


async def _agreement_count(db_conn, vendor_id: int, status: str | None = None) -> int:
    sql = "SELECT count(*) FROM agreement WHERE vendor_id = :v"
    params = {"v": vendor_id}
    if status is not None:
        sql += " AND status = :s"
        params["s"] = status
    return (await db_conn.execute(text(sql), params)).scalar_one()


async def test_toggle_on_inserts_active(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-on")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    assert resp.json()["starred"] is True
    assert await _agreement_count(db_conn, v, "active") == 1


async def test_toggle_off_terminates_active(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-off")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["starred"] is False
    assert await _agreement_count(db_conn, v, "active") == 0
    assert await _agreement_count(db_conn, v, "terminated") == 1


async def test_toggle_on_after_off_creates_new_row(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-reon")
    await f.make_agreement(db_conn, vendor_id=v, status="terminated")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    # новая active-строка, старый terminated НЕ реанимирован
    assert await _agreement_count(db_conn, v) == 2
    assert await _agreement_count(db_conn, v, "active") == 1
    assert await _agreement_count(db_conn, v, "terminated") == 1


async def test_toggle_on_expired_not_resurrected(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-exp")
    await f.make_agreement(db_conn, vendor_id=v, status="expired")
    await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert await _agreement_count(db_conn, v, "expired") == 1  # осталась expired
    assert await _agreement_count(db_conn, v, "active") == 1    # добавлена новая


async def test_toggle_on_when_active_is_noop(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-noop")
    await f.make_agreement(db_conn, vendor_id=v, status="active")
    before = await _agreement_log_count(db_conn, v)
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 200
    # no-op: ни новой строки, ни записи в аудит (UPDATE не выполняется)
    assert await _agreement_count(db_conn, v) == 1
    assert await _agreement_log_count(db_conn, v) == before


async def test_toggle_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="ag-viewer")
    resp = await client.put(f"/vendors/{v}/agreement", json={"active": True})
    assert resp.status_code == 403


async def test_add_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-add")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "AlAdd-2"})
    assert resp.status_code == 201
    assert resp.json()["alias"] == "AlAdd-2"


async def test_add_alias_duplicate_409(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-dup")
    await f.make_alias(db_conn, vendor_id=v, alias="DUP-ALIAS")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "DUP-ALIAS"})
    assert resp.status_code == 409


async def test_add_alias_missing_vendor_404(client, as_admin) -> None:
    resp = await client.post("/vendors/999999/aliases", json={"alias": "x"})
    assert resp.status_code == 404


async def test_remove_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-del")
    aid = await f.make_alias(db_conn, vendor_id=v, alias="al-del-1")
    resp = await client.delete(f"/vendors/{v}/aliases/{aid}")
    assert resp.status_code == 204


async def test_remove_alias_missing_404(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-del-miss")
    resp = await client.delete(f"/vendors/{v}/aliases/999999")
    assert resp.status_code == 404


async def test_alias_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="al-viewer")
    resp = await client.post(f"/vendors/{v}/aliases", json={"alias": "nope"})
    assert resp.status_code == 403
```

Также добавить импорт `text` в начало файла тестов:

```python
from sqlalchemy import text
```

- [ ] **Step 3: Прогнать — падают (эндпоинтов нет)**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -k "toggle or alias" -v`
Expected: FAIL (405/404 — маршрутов нет).

- [ ] **Step 4: Реализовать мутации**

В `backend/app/routers/vendors.py` — расширить импорты и добавить эндпоинты:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import DBAPIError

from ..auth import CurrentUser, require_admin, require_user
from ..db import read_conn, tx
from ..schemas import (
    AgreementToggle,
    AliasCreate,
    VendorAlias,
    VendorCard,
    VendorRepresents,
    WhereAllowed,
    WhereAllowedChip,
    WhereAllowedPosition,
    WhereAllowedStandard,
)
```

```python
async def _ensure_vendor(conn: AsyncConnection, vendor_id: int) -> None:
    exists = (
        await conn.execute(text("SELECT 1 FROM vendor WHERE id = :id"), {"id": vendor_id})
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")


@router.put("/{vendor_id}/agreement")
async def toggle_agreement(
    vendor_id: int,
    body: AgreementToggle,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> dict[str, bool]:
    """Тумблер соглашения (O1). Асимметрично, инвариант «одна активная строка»:
    вкл на уже активном — no-op (UPDATE не выполняем, чтобы не засорять аудит);
    иначе INSERT новой active (историю expired/terminated НЕ реанимируем).
    Выкл — терминируем активную. Аудит пишет триггер (changed_by = app.user)."""
    await _ensure_vendor(conn, vendor_id)
    if body.active:
        has_active = (
            await conn.execute(
                text("SELECT 1 FROM agreement WHERE vendor_id = :id AND status = 'active'"),
                {"id": vendor_id},
            )
        ).scalar_one_or_none()
        if has_active is None:
            await conn.execute(
                text("INSERT INTO agreement (vendor_id, status) VALUES (:id, 'active')"),
                {"id": vendor_id},
            )
    else:
        await conn.execute(
            text(
                "UPDATE agreement SET status = 'terminated' "
                "WHERE vendor_id = :id AND status = 'active'"
            ),
            {"id": vendor_id},
        )
    starred = (
        await conn.execute(text("SELECT vendor_starred(:id)"), {"id": vendor_id})
    ).scalar_one()
    return {"starred": starred}


@router.post(
    "/{vendor_id}/aliases",
    response_model=VendorAlias,
    status_code=status.HTTP_201_CREATED,
)
async def add_alias(
    vendor_id: int,
    body: AliasCreate,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> VendorAlias:
    await _ensure_vendor(conn, vendor_id)
    try:
        row = (
            await conn.execute(
                text(
                    "INSERT INTO vendor_alias (vendor_id, alias) "
                    "VALUES (:v, :a) RETURNING id, alias"
                ),
                {"v": vendor_id, "a": body.alias},
            )
        ).mappings().one()
    except DBAPIError as exc:
        # alias UNIQUE глобально → нарушение уникальности = 409
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой вариант написания уже занят") from exc
    return VendorAlias.model_validate(dict(row))


@router.delete("/{vendor_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_alias(
    vendor_id: int,
    alias_id: int,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    res = await conn.execute(
        text("DELETE FROM vendor_alias WHERE id = :a AND vendor_id = :v"),
        {"a": alias_id, "v": vendor_id},
    )
    if res.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вариант написания не найден")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Прогнать — PASS + регенерировать типы**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -v` — Expected: PASS (все).
Run: `just types` — Expected: `schema.d.ts` содержит `PUT /vendors/{vendor_id}/agreement`, `POST/DELETE …/aliases`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/tests/api/test_vendors.py frontend/src/api/schema.d.ts
git commit -m "feat(api): мутации вендора — тумблер соглашения (O1) + alias CRUD (RBAC admin)"
```

---

## Task 8: Фронт — включить тумблер соглашения и редактирование alias

**Files:**
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`, `VendorCardScreen.test.tsx`
- Modify: `frontend/src/test/msw/handlers.ts`

**Interfaces:**
- Consumes: мутации Task 7 (типы из `schema.d.ts`), `useVendor` queryKey `["vendor", id]`.
- Produces: `useToggleAgreement(id)`, `useAddAlias(id)`, `useRemoveAlias(id)`; интерактивные тумблер/alias в экране.

- [ ] **Step 1: Мутационные хуки с инвалидацией**

В `frontend/src/api/queries.ts` — расширить импорт и добавить хуки:

```ts
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
```

```ts
export function useToggleAgreement(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (active: boolean) => {
      const { data, error } = await api.PUT("/vendors/{vendor_id}/agreement", {
        params: { path: { vendor_id: id } },
        body: { active },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", id] }),
  })
}

export function useAddAlias(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (alias: string) => {
      const { data, error } = await api.POST("/vendors/{vendor_id}/aliases", {
        params: { path: { vendor_id: id } },
        body: { alias },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", id] }),
  })
}

export function useRemoveAlias(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (aliasId: number) => {
      const { error } = await api.DELETE("/vendors/{vendor_id}/aliases/{alias_id}", {
        params: { path: { vendor_id: id, alias_id: aliasId } },
      })
      if (error) throw error
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", id] }),
  })
}
```

- [ ] **Step 2: Падающий тест интерактивности (тумблер шлёт PUT)**

Добавить в `frontend/src/screens/vendors/VendorCardScreen.test.tsx`:

```tsx
describe("VendorCardScreen — мутации", () => {
  it("клик по тумблеру шлёт PUT /agreement", async () => {
    let putBody: unknown = null
    server.use(
      http.put("/api/vendors/:vendorId/agreement", async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json({ starred: false })
      })
    )
    renderAt()
    await screen.findByText("System Air")
    await userEvent.click(
      screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })
    )
    await waitFor(() => expect(putBody).toEqual({ active: false }))
  })

  it("добавление alias шлёт POST", async () => {
    let posted: unknown = null
    server.use(
      http.post("/api/vendors/:vendorId/aliases", async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ id: 9, alias: "NewAlias" }, { status: 201 })
      })
    )
    renderAt()
    await screen.findByText("System Air")
    await userEvent.click(screen.getByRole("button", { name: "+ вариант" }))
    await userEvent.type(
      screen.getByPlaceholderText("вариант написания"),
      "NewAlias"
    )
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }))
    await waitFor(() => expect(posted).toEqual({ alias: "NewAlias" }))
  })
})
```

Требуется импорт `waitFor` (добавить к существующему `@testing-library/react`).

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (тумблер disabled; кнопки «+ вариант» нет).

- [ ] **Step 3: Сделать тумблер и alias-редактирование интерактивными**

В `frontend/src/screens/vendors/VendorCardScreen.tsx`:

1) импорты — добавить `useState` и мутационные хуки:

```tsx
import { useState } from "react"

import {
  useAddAlias,
  useRemoveAlias,
  useToggleAgreement,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import { X } from "lucide-react"
```

2) в теле компонента — инстанцировать мутации и локальный стейт формы alias:

```tsx
  const toggleAgreement = useToggleAgreement(id)
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")
```

3) заменить `Switch` в шапке на интерактивный:

```tsx
            <Switch
              checked={data.starred}
              disabled={toggleAgreement.isPending}
              onCheckedChange={(next) => toggleAgreement.mutate(next)}
              aria-label="Соглашение о сотрудничестве"
            />
```

4) заменить блок alias-чипов на вариант с удалением и инлайн-добавлением:

```tsx
        <div className="flex flex-wrap items-center gap-1.5">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">—</span>
          )}
          {data.aliases.map((a) => (
            <Badge key={a.id} variant="outline" className="gap-1">
              {a.alias}
              <button
                type="button"
                aria-label={`удалить ${a.alias}`}
                onClick={() => removeAlias.mutate(a.id)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          {aliasOpen ? (
            <span className="flex items-center gap-1">
              <input
                autoFocus
                value={aliasDraft}
                onChange={(e) => setAliasDraft(e.target.value)}
                placeholder="вариант написания"
                className="h-7 rounded-sm border bg-transparent px-2 text-small"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={aliasDraft.trim() === "" || addAlias.isPending}
                onClick={() => {
                  addAlias.mutate(aliasDraft.trim(), {
                    onSuccess: () => {
                      setAliasDraft("")
                      setAliasOpen(false)
                    },
                  })
                }}
              >
                Добавить
              </Button>
            </span>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setAliasOpen(true)}>
              + вариант
            </Button>
          )}
        </div>
```

> `size="sm"` уже есть в DS `button` (проверить `buttonVariants`); если нет — убрать проп.

- [ ] **Step 4: Прогнать — PASS**

Run: `cd frontend; npm run test -- VendorCardScreen`
Expected: PASS. Run: `cd frontend; npm run typecheck` — без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx frontend/src/test/msw/handlers.ts
git commit -m "feat(vendors): интерактивный тумблер соглашения + добавление/удаление alias"
```

---

## Task 9: Финализация — `just ci`, документация

**Files:**
- Modify: `CLAUDE.md`, `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-11-vendor-card.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли` (types, lint, typecheck, test — backend pytest + frontend vitest).
Если db-тесты скипаются локально (нет `DATABASE_URL_TEST`) — это ок; они прогонятся в CI на эфемерной ветке Neon.

- [ ] **Step 2: TECH_DEBT**

Добавить в `docs/TECH_DEBT.md` пункты:
- Агрегация «Где разрешён» по brand-key на карточке владельца (O3) — сейчас только листинги самого вендора.
- Поток «Объединить» (O2) — из заглушки в диалог + перенос listing представляемого вендора.
- Ленивое раскрытие «Где разрешён» по стандарту, если у вендора сотни позиций.

- [ ] **Step 3: CLAUDE.md**

- §5 (порядок работ): отметить карточку вендора как срез (read + мутации соглашения/alias), кликабельность матрицы.
- Карта репо: `screens/vendors/` (VendorCardScreen + model.ts), роутер `vendors`, роут `/vendors/$vendorId`, DS-примитивы `switch`/`accordion`, миграция `0005_vendor_where_allowed`.

- [ ] **Step 4: Devlog**

Create `docs/devlog/2026-07-11-vendor-card.md` — хронология: правило исключения одной истиной в SQL, два read-эндпоинта, асимметрия тумблера (O1) и почему (не реанимировать историю), кликабельность без правки бэкенда (vendor_id уже в payload), развилки O1–O4.

- [ ] **Step 5: Commit + push + PR**

```bash
git add CLAUDE.md docs/TECH_DEBT.md docs/devlog/2026-07-11-vendor-card.md
git commit -m "docs(vendor-card): devlog + CLAUDE.md §5/карта + TECH_DEBT (O2/O3/ленивое дерево)"
git push -u origin feat/vendor-card
gh pr create --base main --title "feat: карточка вендора + кликабельные вендоры в каталоге" --body "..."
```

---

## Self-Review

**Spec coverage:**
- Правило исключения (4 кейса) → Task 1 (db-тесты а/б/в/г + детерминизм + порядок). ✓
- `GET /vendors/{id}` (шапка/note/aliases/represents/обратный счётчик) → Task 2. ✓
- `GET /vendors/{id}/where-allowed` (дерево) → Task 3. ✓
- Экран: шапка/note/aliases/бренд → Task 4; «Где разрешён» + зачёркнутые чипы + тултип + легенда → Task 5. ✓
- Кликабельность матрицы (vendor_id уже в payload, только вендор-теги) → Task 6. ✓
- Мутации: тумблер O1 (асимметрия, no-op, не реанимировать; аудит) + alias CRUD (уникальность 409) + RBAC → Task 7; фронт-обвязка → Task 8. ✓
- DS `switch`/`accordion`, без новых цвет-токенов → Task 4/5. ✓
- Локализация kind (все три), терминология → model.ts (Task 4). ✓
- Заглушка «Объединить» (O2), не показывать brand-key (O3), тултип с label (O4) → Task 4/5/7 + TECH_DEBT (Task 9). ✓
- Границы (список `/vendors`, поток объединения, история agreement в UI, поля signed_on и т.п.) — вне объёма, не реализуются. ✓

**Placeholder scan:** код в каждом шаге полный; «...» только в `gh pr create --body` (Task 9) — заполняется при создании PR. Явных TODO/TBD нет.

**Type consistency:** path-параметры — `vendor_id`/`alias_id` сквозь бэкенд-роуты, `schema.d.ts` и фронт-хуки (`params.path.vendor_id`). Схемы `VendorCard`/`WhereAllowed*`/`AgreementToggle`/`AliasCreate` — одни имена в схемах, роутере, тестах. queryKey `["vendor", id]` инвалидируется мутациями (Task 8) — совпадает с `useVendor` (Task 4). Хуки `useVendor`/`useVendorWhereAllowed`/`useToggleAgreement`/`useAddAlias`/`useRemoveAlias` — согласованы между queries.ts и экраном.
