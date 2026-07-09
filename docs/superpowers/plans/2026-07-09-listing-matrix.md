# Матрица перечня — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Первый продуктовый read-only экран — матрица перечня (позиции × классы), с серверной пагинацией по позициям, группировкой колонок, деревом разделов, фильтром/поиском.

**Architecture:** Server pivot — новый эндпоинт `GET /listings/matrix` шейпит плоскую вьюху `listing_live` в позиции-строки с массивом ячеек (без новой вьюхи, звезда/статусы как есть). Пагинация по различным позициям в кураторском порядке (новая SQL-функция `category_sort_path`). Фронт — TanStack Router (типизированный URL-контракт фильтров) + TanStack Table (группы колонок) + TanStack Query, на DS-компонентах `table`/`badge`/`card`.

**Tech Stack:** FastAPI + SQLAlchemy Core (asyncpg), Alembic (чистый SQL), Pydantic v2; Vite + React 19 + TS, TanStack Router/Table/Query, shadcn/Tailwind (DS-токены), Vitest + MSW.

**Спека (источник истины):** [docs/superpowers/specs/2026-07-09-listing-matrix-design.md](../specs/2026-07-09-listing-matrix-design.md) (r5).

## Global Constraints

- **Schema-first.** БД — источник истины. ORM запрещён; только SQLAlchemy Core (сырой SQL). Вычислимое (звезда `vendor_starred`, статусы) НЕ пересчитывать в коде — брать из `listing_live` как есть.
- **Миграции — только новыми ревизиями чистым SQL** (`just makemigration` + `op.execute`). Базовые `0001_core`/`0002_compliance` и файлы `sql/*.sql` НЕ трогать.
- **Экран строго read-only.** Никаких пишущих эндпоинтов/мутаций. Чтение — через `Depends(read_conn)`.
- **Роли.** `/listings/*` защищён `require_user` (viewer достаточно) — уже так на роутере.
- **Ветка** `feat/listing-matrix`, PR в `main`. Перед пушем — `just ci` зелёный (types → lint → typecheck → test). Не коммитить в `main` напрямую.
- **Логирование.** Логгер `logging.getLogger(__name__)`, не `print`.
- **Кириллица в PowerShell** — все just-рецепты уже форсируют UTF-8; пользуйся `just`, а не ручными командами.

---

## Файловая структура

**Backend:**
- Create: `backend/migrations/versions/0003_category_sort_path.py` — ревизия с `category_sort_path`.
- Modify: `backend/app/schemas/__init__.py` — модели `Matrix*`/`SegmentRef`/`SegmentGroupRef`.
- Modify: `backend/app/routers/listings.py` — эндпоинт `GET /listings/matrix` + хелпер группировки колонок.
- Create: `backend/tests/db/test_category_sort_path.py` — db-тест функции.
- Create: `backend/tests/db/test_matrix.py` — db-тест эндпоинта (свойства данных).
- Create: `backend/tests/api/test_matrix.py` — api-тест (форма/коды).

**Frontend:**
- Create: `frontend/src/components/ui/table.tsx`, `badge.tsx`, `card.tsx` (+ `*.test.tsx`).
- Create: `frontend/src/router.tsx` — code-based дерево маршрутов.
- Create: `frontend/src/screens/DesignSystemShowcase.tsx` — перенос витрины из `App.tsx`.
- Create: `frontend/src/screens/matrix/MatrixScreen.tsx` — экран.
- Create: `frontend/src/screens/matrix/model.ts` (+ `model.test.ts`) — чистые хелперы (`withSectionHeaders`, `cellFor`).
- Create: `frontend/src/screens/matrix/columns.tsx` — `buildColumnDefs`, `renderCell`.
- Create: `frontend/src/screens/matrix/MatrixScreen.test.tsx` — MSW-интеграция.
- Create: `frontend/src/test/msw/handlers.ts`, `frontend/src/test/msw/server.ts`.
- Modify: `frontend/src/test/setup.ts` — жизненный цикл MSW.
- Modify: `frontend/src/api/queries.ts` — `useMatrix`/`useBuildingTypes`/`useSegments`.
- Modify: `frontend/src/main.tsx` — `RouterProvider`.
- Delete: `frontend/src/App.tsx` (содержимое ушло в `DesignSystemShowcase`).
- Modify: `frontend/src/api/schema.d.ts` — регенерация `just types` (не руками).

---

## Task 0: Preflight — сверить сигнатуры и конфиг с репозиторием

Три факта, от которых зависит корректность Task 1/2/7/9. Сверить **фактом из кода**, не догадкой, ДО написания кода. Все три уже проверены при написании плана и зафиксированы ниже — Task 0 подтверждает, что в репо ничего не поехало с тех пор.

- [ ] **Step 1: Сигнатура `category_path`**

Run: `cd backend; grep -n "FUNCTION category_path" migrations/sql/0001_core_schema.sql`
Ожидаемо: `CREATE FUNCTION category_path(p_id int) RETURNS text` — аргумент это **id категории** (внутри `WHERE id = p_id` по таблице `category`; в `listing_live`/`freeze_release` зовётся как `category_path(pos.category_id)`). Значит `category_sort_path` (Task 1) тоже принимает **id категории**, и вызовы `category_path(p.category_id)` / `category_sort_path(p.category_id)` в Task 2 корректны и согласованы. Если сигнатура иная — остановись и приведи `category_sort_path` к тому же типу аргумента, что и близнец.

- [ ] **Step 2: `baseUrl` клиента**

Run: `grep -n "baseUrl" frontend/src/api/client.ts`
Ожидаемо: `const baseUrl = import.meta.env.VITE_API_URL ?? "/api"` — дефолт `/api`. Значит MSW-хендлеры (Task 7) бьют по `/api/...` (`BASE = "/api"`). Если дефолт иной — выставь `BASE` строго под него, иначе `onUnhandledRequest:"error"` уронит тесты экрана не по своей вине.

- [ ] **Step 3: Политика `undefined` от openapi-fetch**

`api.GET(...)` из openapi-fetch типизирует `data` как `T | undefined`. Поэтому все хуки в Task 7 сужают тип в `queryFn` через `if (!data) throw ...` (возвращают `T`, не `T | undefined`) — иначе `npm run typecheck` встанет на обращениях без `?.`. Это учтено в коде Task 7; Step 3 — напоминание не «упростить» его обратно.

Preflight ничего не коммитит (сверки). Расхождение — стоп и правка соответствующей задачи до старта.

---

## Task 1: Миграция `category_sort_path`

Функция-близнец `category_path`, отдаёт `int[]` — пары `[sort_order, id]` на каждый уровень предка (root→leaf). Даёт детерминированный preorder даже при дублях `sort_order`.

**Files:**
- Create: `backend/migrations/versions/0003_category_sort_path.py`
- Test: `backend/tests/db/test_category_sort_path.py`

**Interfaces:**
- Produces: SQL-функция `category_sort_path(p_id int) RETURNS int[]` (STABLE).

- [ ] **Step 1: Создать пустую ревизию**

Run: `just makemigration name="category_sort_path"`
Появится файл `backend/migrations/versions/<hash>_category_sort_path.py`. Переименуй его в `0003_category_sort_path.py` и задай явные ревизии (стиль репо).

- [ ] **Step 2: Написать тело ревизии**

`backend/migrations/versions/0003_category_sort_path.py`:

```python
"""Ревизия №3: функция сортировочного пути раздела (презентация, read-only).

category_sort_path(category_id) -> int[] — пары [sort_order, id] на уровень предка
(root→leaf). Массивное сравнение даёт детерминированный preorder даже при дублях
sort_order. Порядок отображения матрицы (spec §Выборка), инвариант не трогаем.

Revision ID: 0003_category_sort_path
Revises: 0002_compliance
"""

from __future__ import annotations

from alembic import op

revision = "0003_category_sort_path"
down_revision = "0002_compliance"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION category_sort_path(p_id int) RETURNS int[]
  LANGUAGE sql STABLE AS
$$
    WITH RECURSIVE up AS (
        SELECT id, parent_id, sort_order, 1 AS lvl FROM category WHERE id = p_id
        UNION ALL
        SELECT c.id, c.parent_id, c.sort_order, up.lvl + 1
        FROM category c JOIN up ON c.id = up.parent_id
    )
    SELECT array_agg(v ORDER BY lvl DESC, ord)
    FROM up
    CROSS JOIN LATERAL (VALUES (0, sort_order), (1, id)) AS pair(ord, v);
$$;
"""

_DOWN = "DROP FUNCTION IF EXISTS category_sort_path(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
```

- [ ] **Step 3: Накатить на тест-ветку**

Run: `just migrate-test`
Expected: применится `0003_category_sort_path` (на прод не льём).

- [ ] **Step 4: Написать падающий db-тест**

`backend/tests/db/test_category_sort_path.py`:

```python
"""category_sort_path: preorder по кураторскому sort_order, детерминизм при дублях.
Логика в БД — ждём PASS сразу (инвертированный TDD для db-тестов)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _csp(db_conn, cat_id: int) -> list[int]:
    return (
        await db_conn.execute(
            text("SELECT category_sort_path(:c)"), {"c": cat_id}
        )
    ).scalar_one()


async def test_preorder_by_sort_order_not_alphabet(db_conn) -> None:
    # Родитель, под ним "Вентиляция" (sort_order=2) и "ОВиК" (sort_order=1):
    # алфавит дал бы Вентиляцию первой, курация требует ОВиК первым.
    root = await f.make_category(db_conn, name="Оборудование")
    vent = await f.make_category(db_conn, name="Вентиляция", parent_id=root)
    ovik = await f.make_category(db_conn, name="ОВиК", parent_id=root)
    await db_conn.execute(text("UPDATE category SET sort_order = 2 WHERE id = :i"), {"i": vent})
    await db_conn.execute(text("UPDATE category SET sort_order = 1 WHERE id = :i"), {"i": ovik})

    csp_ovik = await _csp(db_conn, ovik)
    csp_vent = await _csp(db_conn, vent)
    assert csp_ovik < csp_vent  # ОВиК раньше Вентиляции по курации


async def test_deterministic_on_duplicate_sort_order(db_conn) -> None:
    # Два раздела под общим родителем с ОДИНАКОВЫМ sort_order → устойчивый
    # порядок по id (пара [sort_order, id]).
    root = await f.make_category(db_conn, name="Корень")
    a = await f.make_category(db_conn, name="A", parent_id=root)
    b = await f.make_category(db_conn, name="B", parent_id=root)
    await db_conn.execute(text("UPDATE category SET sort_order = 5 WHERE id IN (:a, :b)"), {"a": a, "b": b})
    csp_a = await _csp(db_conn, a)
    csp_b = await _csp(db_conn, b)
    assert csp_a < csp_b  # a.id < b.id → детерминировано, не случайно


async def test_parent_prefixes_child(db_conn) -> None:
    root = await f.make_category(db_conn, name="Корень")
    child = await f.make_category(db_conn, name="Лист", parent_id=root)
    csp_root = await _csp(db_conn, root)
    csp_child = await _csp(db_conn, child)
    assert csp_child[: len(csp_root)] == csp_root  # путь ребёнка начинается с пути родителя
```

- [ ] **Step 5: Запустить тест**

Run: `just test` (или `cd backend; uv run pytest tests/db/test_category_sort_path.py -v`)
Expected: 3 PASS (функция уже накачена в Step 3). Если тест-ветка недоступна — тесты скипнутся; тогда накати `just migrate-test` и повтори.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0003_category_sort_path.py backend/tests/db/test_category_sort_path.py
git commit -m "feat(matrix): миграция category_sort_path (int[] preorder) + db-тест"
```

---

## Task 2: Эндпоинт `GET /listings/matrix`

Server pivot: колонки из payload, строки-позиции с массивом ячеек, пагинация по позициям. Перформанс — часть задачи: пути считаются один раз на категорию (CTE `cats`), не тянутся из вьюхи на каждый ряд.

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/listings.py`
- Test: `backend/tests/db/test_matrix.py`, `backend/tests/api/test_matrix.py`

**Interfaces:**
- Consumes: `category_sort_path` (Task 1), `read_conn` ([db.py](../../../backend/app/db.py)), `require_user`.
- Produces: `GET /listings/matrix?building_type_id&segment_id?&q?&limit&offset` → `Matrix`. Модели `MatrixVendorRef`/`MatrixCell`/`MatrixRow`/`SegmentRef`/`SegmentGroupRef`/`MatrixColumnGroup`/`Matrix`.

- [ ] **Step 1: Добавить Pydantic-модели**

В `backend/app/schemas/__init__.py`, после блока `# --- Живой перечень (listing_live)` (рядом с `ListingRow`), добавь:

```python
# --- Матрица перечня (server pivot над listing_live) ------------------------
class MatrixVendorRef(BaseModel):
    vendor_id: int
    name: str
    starred: bool          # = vendor_starred, как есть
    ujin_integration: bool
    note: str | None       # per-vendor (атрибут ряда)


class MatrixCell(BaseModel):
    segment_id: int
    vendors: list[MatrixVendorRef]  # непусто ⇒ вендорная ячейка
    spec_text: str | None           # требование (vendor NULL)
    note: str | None                # значим только для ячейки-требования


class MatrixRow(BaseModel):
    position_id: int
    position_name: str
    category_path: str              # position.category_id NOT NULL ⇒ путь всегда есть
    cells: list[MatrixCell]


class SegmentRef(BaseModel):
    id: int
    name: str
    sort_order: int


class SegmentGroupRef(BaseModel):
    id: int
    name: str


class MatrixColumnGroup(BaseModel):
    group: SegmentGroupRef | None   # None ⇒ плоские leaf-колонки (жилые/социальные)
    segments: list[SegmentRef]


class Matrix(BaseModel):
    columns: list[MatrixColumnGroup]
    items: list[MatrixRow]
    total: int                      # число РАЗЛИЧНЫХ позиций под фильтром
    limit: int
    offset: int
```

- [ ] **Step 2: Написать падающий db-тест**

`backend/tests/db/test_matrix.py`:

```python
"""GET /listings/matrix поверх listing_live: server pivot, пагинация по позициям,
группировка колонок, звезда как есть, стык q×segment_id. Изоляция — фильтр по
свежесозданным данным (БД штатно заполнена сидом)."""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _office_segments(db_conn):
    """id классов офиса: (Prime, Класс А, Класс B — группа 'Офисные здания'), ТРЦ."""
    rows = (
        await db_conn.execute(
            text(
                "SELECT s.name, s.id FROM segment s "
                "JOIN building_type bt ON bt.id = s.building_type_id WHERE bt.code = 'office'"
            )
        )
    ).all()
    return {name: sid for name, sid in rows}


async def test_row_not_torn_and_star_as_is(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg_biz = await f.get_segment_id(db_conn, name="Бизнес")
    seg_eco = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="МатрицаТест-Оборудование")
    pos = await f.make_position(db_conn, category_id=cat, name="МатрицаТест-Насосы")
    v = await f.make_vendor(db_conn, name="Mtx-Grundfos")
    await f.make_agreement(db_conn, vendor_id=v, status="active")  # звезда
    await f.make_listing(db_conn, position_id=pos, segment_id=seg_biz, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg_eco, vendor_id=None,
                         status="requirement", spec_text="Россия")

    resp = await client.get("/listings/matrix", params={"building_type_id": bt, "q": "МатрицаТест-Насосы"})
    assert resp.status_code == 200
    body = resp.json()
    row = next(r for r in body["items"] if r["position_id"] == pos)
    # Обе ячейки позиции на одной странице (строка не порвана):
    by_seg = {c["segment_id"]: c for c in row["cells"]}
    assert by_seg[seg_biz]["vendors"][0]["name"] == "Mtx-Grundfos"
    assert by_seg[seg_biz]["vendors"][0]["starred"] is True   # звезда из БД как есть
    assert by_seg[seg_eco]["vendors"] == [] and by_seg[seg_eco]["spec_text"] == "Россия"
    assert body["total"] >= 1 and body["limit"] == 50 and body["offset"] == 0


async def test_office_column_grouping(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="office")
    resp = await client.get("/listings/matrix", params={"building_type_id": bt})
    assert resp.status_code == 200
    cols = resp.json()["columns"]
    groups = {g["group"]["name"]: [s["name"] for s in g["segments"]] for g in cols if g["group"]}
    assert groups["Офисные здания"] == ["Prime", "Класс А", "Класс B"]
    assert groups["ТРЦ"] == ["ТРЦ"]


async def test_residential_columns_flat(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    cols = (await client.get("/listings/matrix", params={"building_type_id": bt})).json()["columns"]
    assert all(g["group"] is None for g in cols)  # жилые — без групп
    flat = [s["name"] for g in cols for s in g["segments"]]
    assert "Бизнес" in flat and len(flat) == 6


async def test_segment_id_narrows_columns(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cols = (await client.get("/listings/matrix",
            params={"building_type_id": bt, "segment_id": seg})).json()["columns"]
    seg_ids = [s["id"] for g in cols for s in g["segments"]]
    assert seg_ids == [seg]  # ровно одна колонка


async def test_q_with_segment_id_excludes_empty_in_class(client, as_viewer, db_conn) -> None:
    # Позиция матчит q по пути, но НЕ имеет ряда в суженном сегменте → отсутствует.
    bt = await f.get_building_type_id(db_conn, code="residential")
    seg_biz = await f.get_segment_id(db_conn, name="Бизнес")
    seg_eco = await f.get_segment_id(db_conn, name="Эконом")
    cat = await f.make_category(db_conn, name="УникПутьZZ")
    pos = await f.make_position(db_conn, category_id=cat, name="ПозицияZZ")
    v = await f.make_vendor(db_conn, name="Zz-Vendor")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg_biz, vendor_id=v, status="allowed")

    # q по пути "УникПутьZZ", но сужаем на Эконом, где ряда нет → позиции нет.
    body = (await client.get("/listings/matrix",
            params={"building_type_id": bt, "segment_id": seg_eco, "q": "УникПутьZZ"})).json()
    assert all(r["position_id"] != pos for r in body["items"])
    # А без сужения (или на Бизнес) — позиция есть:
    body2 = (await client.get("/listings/matrix",
             params={"building_type_id": bt, "segment_id": seg_biz, "q": "УникПутьZZ"})).json()
    assert any(r["position_id"] == pos for r in body2["items"])
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/db/test_matrix.py -v`
Expected: FAIL 404 (роут `/listings/matrix` ещё не объявлен).

- [ ] **Step 4: Реализовать эндпоинт**

В `backend/app/routers/listings.py` обнови импорт схем и добавь хелпер + роут. Импорт:

```python
from ..schemas import (
    ListingRow,
    Matrix,
    MatrixCell,
    MatrixColumnGroup,
    MatrixRow,
    MatrixVendorRef,
    Page,
    SegmentGroupRef,
    SegmentRef,
)
```

Хелпер группировки колонок (над функцией `list_listings`):

```python
def _group_columns(col_rows: list[dict[str, Any]]) -> list[MatrixColumnGroup]:
    """Свернуть упорядоченные строки сегментов в группы (consecutive by group_id).
    group_id NULL → одна группа с group=None (жилые/социальные)."""
    columns: list[MatrixColumnGroup] = []
    for r in col_rows:
        seg = SegmentRef(id=r["segment_id"], name=r["segment_name"], sort_order=r["seg_sort"])
        gid = r["group_id"]
        last_gid = columns[-1].group.id if (columns and columns[-1].group) else None
        if columns and last_gid == gid:
            columns[-1].segments.append(seg)
        else:
            grp = SegmentGroupRef(id=gid, name=r["group_name"]) if gid is not None else None
            columns.append(MatrixColumnGroup(group=grp, segments=[seg]))
    return columns
```

Роут (после `list_listings`):

```python
@router.get("/matrix", response_model=Matrix)
async def listing_matrix(
    building_type_id: int,
    segment_id: int | None = None,
    q: str | None = Query(None, description="Поиск по позиции/вендору/разделу"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: AsyncConnection = Depends(read_conn),
) -> Matrix:
    seg_f = "AND ll.segment_id = :seg" if segment_id is not None else ""
    q_f = (
        "AND (ll.position_name ILIKE :q OR ll.vendor_name ILIKE :q OR ll.category_path ILIKE :q)"
        if q
        else ""
    )
    params: dict[str, Any] = {"bt": building_type_id}
    if segment_id is not None:
        params["seg"] = segment_id
    if q:
        params["q"] = f"%{q}%"

    total = (
        await conn.execute(
            text(
                "SELECT count(*) FROM (SELECT DISTINCT ll.position_id FROM listing_live ll "
                "WHERE ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
                f"{seg_f} {q_f}) t"
            ),
            params,
        )
    ).scalar_one()

    page = (
        await conn.execute(
            text(
                f"""
                WITH pos_page AS (
                    SELECT DISTINCT ll.position_id
                    FROM listing_live ll
                    WHERE ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt)
                      {seg_f} {q_f}
                ),
                cats AS (
                    SELECT DISTINCT p.category_id,
                           category_sort_path(p.category_id) AS csp,
                           category_path(p.category_id)      AS cpath
                    FROM pos_page pp JOIN position p ON p.id = pp.position_id
                )
                SELECT p.id AS position_id, p.name AS position_name, c.cpath AS category_path
                FROM pos_page pp
                JOIN position p ON p.id = pp.position_id
                JOIN cats c     ON c.category_id = p.category_id
                ORDER BY c.csp, p.sort_order, p.id
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )
    ).mappings().all()

    position_ids = [r["position_id"] for r in page]
    cells_by_pos: dict[int, dict[int, dict[str, Any]]] = {}
    if position_ids:
        cell_params: dict[str, Any] = {"bt": building_type_id, "pos_ids": position_ids}
        if segment_id is not None:
            cell_params["seg"] = segment_id
        cell_rows = (
            await conn.execute(
                text(
                    f"""
                    SELECT ll.position_id, ll.segment_id, ll.vendor_id, ll.vendor_name,
                           ll.vendor_starred, ll.ujin_integration, ll.spec_text, ll.note
                    FROM listing_live ll
                    WHERE ll.position_id = ANY(:pos_ids)
                      AND ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt)
                      {seg_f}
                    ORDER BY ll.position_id, ll.segment_id, ll.sort_order, ll.id
                    """
                ),
                cell_params,
            )
        ).mappings().all()
        for cr in cell_rows:
            seg_map = cells_by_pos.setdefault(cr["position_id"], {})
            cell = seg_map.setdefault(
                cr["segment_id"],
                {"segment_id": cr["segment_id"], "vendors": [], "spec_text": None, "note": None},
            )
            if cr["vendor_id"] is not None:
                cell["vendors"].append(
                    {
                        "vendor_id": cr["vendor_id"],
                        "name": cr["vendor_name"],
                        "starred": cr["vendor_starred"],
                        "ujin_integration": cr["ujin_integration"],
                        "note": cr["note"],
                    }
                )
            else:
                cell["spec_text"] = cr["spec_text"]
                cell["note"] = cr["note"]

    items = [
        MatrixRow(
            position_id=r["position_id"],
            position_name=r["position_name"],
            category_path=r["category_path"],
            cells=[MatrixCell(**c) for c in cells_by_pos.get(r["position_id"], {}).values()],
        )
        for r in page
    ]

    col_params: dict[str, Any] = {"bt": building_type_id}
    col_seg_f = ""
    if segment_id is not None:
        col_params["seg"] = segment_id
        col_seg_f = "AND s.id = :seg"
    col_rows = (
        await conn.execute(
            text(
                f"""
                SELECT s.id AS segment_id, s.name AS segment_name, s.sort_order AS seg_sort,
                       sg.id AS group_id, sg.name AS group_name
                FROM segment s
                LEFT JOIN segment_group sg ON sg.id = s.group_id
                WHERE s.building_type_id = :bt {col_seg_f}
                ORDER BY COALESCE(sg.sort_order, -1), s.sort_order, s.id
                """
            ),
            col_params,
        )
    ).mappings().all()

    return Matrix(
        columns=_group_columns([dict(r) for r in col_rows]),
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
```

> **Порядок колонок:** `ORDER BY COALESCE(sg.sort_order, -1), …` кладёт бесгрупповые сегменты (`-1`) перед группами. В засеянных данных это неважно: жилые/социальные — все без групп, офис — все в группах (смешанного типа объекта нет). Если появится тип, где часть сегментов в группе, а часть нет — порядок бесгрупповых окажется в начале; пересмотреть тогда.

- [ ] **Step 5: Запустить db-тест**

Run: `cd backend; uv run pytest tests/db/test_matrix.py -v`
Expected: все PASS. (Если скип — нет `DATABASE_URL_TEST`; накати `just migrate-test` и задай URL.)

- [ ] **Step 6: Написать api-тест (форма/коды, без db-специфики)**

`backend/tests/api/test_matrix.py`:

```python
"""GET /listings/matrix: контракт (обязательность building_type_id, форма ответа)."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_requires_building_type_id(client, as_viewer) -> None:
    resp = await client.get("/listings/matrix")
    assert resp.status_code == 422  # building_type_id обязателен


async def test_shape_keys(client, as_viewer, db_conn) -> None:
    bt = await f.get_building_type_id(db_conn, code="residential")
    body = (await client.get("/listings/matrix", params={"building_type_id": bt})).json()
    assert set(body) == {"columns", "items", "total", "limit", "offset"}
    assert isinstance(body["columns"], list) and isinstance(body["items"], list)
```

- [ ] **Step 7: Запустить api-тест + весь backend**

Run: `cd backend; uv run pytest tests/api/test_matrix.py tests/db/test_matrix.py -v`
Expected: PASS.

- [ ] **Step 8: Регенерировать TS-типы**

Run: `just types`
Изменится `frontend/src/api/schema.d.ts` (появится `/listings/matrix` и схемы `Matrix*`). Файл коммить.

- [ ] **Step 9: Проверить backend lint/typecheck**

Run: `cd backend; uv run ruff check .; uv run mypy app`
Expected: без ошибок.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/listings.py \
  backend/tests/db/test_matrix.py backend/tests/api/test_matrix.py frontend/src/api/schema.d.ts
git commit -m "feat(matrix): эндпоинт GET /listings/matrix (server pivot) + тесты + TS-типы"
```

---

## Task 3: DS-компонент `table`

shadcn table-примитивы на DS-токенах. Только то, что нужно матрице.

**Files:**
- Create: `frontend/src/components/ui/table.tsx`, `frontend/src/components/ui/table.test.tsx`

**Interfaces:**
- Produces: `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` (React-компоненты, пробрасывают `className`).

- [ ] **Step 1: Написать падающий тест**

`frontend/src/components/ui/table.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table"

describe("Table", () => {
  it("рендерит семантическую таблицу с ячейками", () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Позиция</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Насосы</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )
    expect(screen.getByRole("columnheader", { name: "Позиция" })).toBeInTheDocument()
    expect(screen.getByRole("cell", { name: "Насосы" })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/components/ui/table.test.tsx`
Expected: FAIL (модуль не найден).

- [ ] **Step 3: Реализовать `table.tsx`**

`frontend/src/components/ui/table.tsx` (реколор через DS-переменные, как `button.tsx`):

```tsx
import * as React from "react"

import { cn } from "@/lib/utils"

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-body", className)} {...props} />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("[&_tr]:border-b [&_tr]:border-border", className)} {...props} />
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn("border-b border-border transition-colors hover:bg-muted/50", className)}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      className={cn(
        "h-10 px-3 text-left align-middle text-caption font-medium text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-3 py-2 align-top", className)} {...props} />
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell }
```

- [ ] **Step 4: Запустить — проходит**

Run: `cd frontend; npx vitest run src/components/ui/table.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/table.tsx frontend/src/components/ui/table.test.tsx
git commit -m "feat(ui): DS-компонент table (реколор на токенах)"
```

---

## Task 4: DS-компонент `badge`

Для чипов вендоров, маркера звезды/Ujin, текстовых требований.

**Files:**
- Create: `frontend/src/components/ui/badge.tsx`, `frontend/src/components/ui/badge.test.tsx`

**Interfaces:**
- Produces: `Badge` с `variant?: "default" | "outline" | "requirement"`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/components/ui/badge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Badge } from "./badge"

describe("Badge", () => {
  it("рендерит содержимое и вариант", () => {
    render(<Badge variant="requirement">Россия</Badge>)
    expect(screen.getByText("Россия")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/components/ui/badge.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Реализовать `badge.tsx`**

`frontend/src/components/ui/badge.tsx`:

```tsx
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-caption font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        requirement: "border-transparent bg-muted text-muted-foreground italic",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
```

- [ ] **Step 4: Запустить — проходит**

Run: `cd frontend; npx vitest run src/components/ui/badge.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/badge.tsx frontend/src/components/ui/badge.test.tsx
git commit -m "feat(ui): DS-компонент badge (default/outline/requirement)"
```

---

## Task 5: DS-компонент `card`

Контейнер панели фильтров / обёртка матрицы.

**Files:**
- Create: `frontend/src/components/ui/card.tsx`, `frontend/src/components/ui/card.test.tsx`

**Interfaces:**
- Produces: `Card`, `CardHeader`, `CardTitle`, `CardContent`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/components/ui/card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Card, CardContent, CardHeader, CardTitle } from "./card"

describe("Card", () => {
  it("рендерит заголовок и содержимое", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Фильтры</CardTitle>
        </CardHeader>
        <CardContent>тело</CardContent>
      </Card>
    )
    expect(screen.getByText("Фильтры")).toBeInTheDocument()
    expect(screen.getByText("тело")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/components/ui/card.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Реализовать `card.tsx`**

`frontend/src/components/ui/card.tsx`:

```tsx
import * as React from "react"

import { cn } from "@/lib/utils"

function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("rounded-lg border border-border bg-card text-card-foreground shadow-elevation-2", className)}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1 p-4", className)} {...props} />
}

function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return <h3 className={cn("text-body font-medium", className)} {...props} />
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-4 pt-0", className)} {...props} />
}

export { Card, CardHeader, CardTitle, CardContent }
```

- [ ] **Step 4: Запустить — проходит**

Run: `cd frontend; npx vitest run src/components/ui/card.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/card.tsx frontend/src/components/ui/card.test.tsx
git commit -m "feat(ui): DS-компонент card (контейнер на токенах)"
```

---

## Task 6: Роутинг (TanStack Router) + перенос витрины DS

Вводим роутер: `/` → матрица (пока заглушка-компонент), `/design-system` → перенесённая витрина. Дефолт `building_type_id` — в loader'е.

**Files:**
- Install: `@tanstack/react-router`
- Create: `frontend/src/router.tsx`, `frontend/src/screens/DesignSystemShowcase.tsx`, `frontend/src/screens/matrix/MatrixScreen.tsx` (временная заглушка — заполнится в Task 9)
- Modify: `frontend/src/main.tsx`
- Delete: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `router` (экспорт из `router.tsx`), маршрут `matrixRoute` с типизированным `validateSearch`. `MatrixScreen` — компонент маршрута `/`.

- [ ] **Step 1: Установить TanStack Router**

Run: `cd frontend; npm install @tanstack/react-router@^1`
Expected: добавлен в `dependencies`.

- [ ] **Step 2: Перенести витрину DS**

Создай `frontend/src/screens/DesignSystemShowcase.tsx` — скопируй туда ТЕЛО из текущего `frontend/src/App.tsx` (компоненты `Swatch` + разметку из `App`), переименовав экспортируемую функцию в `DesignSystemShowcase`:

```tsx
import { Button } from "@/components/ui/button"

function Swatch({ label, className }: { label: string; className: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className={`h-12 w-full rounded-md border border-border ${className}`} />
      <span className="text-caption text-muted-foreground">{label}</span>
    </div>
  )
}

export function DesignSystemShowcase() {
  return (
    <div className="min-h-svh bg-background p-8 text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="font-display text-h2">MR Design System</h1>
          <p className="text-body text-muted-foreground">
            Проверка токенов и тем. Нажмите <kbd>d</kbd> для переключения темы.
          </p>
        </header>
        <section className="flex flex-col gap-3">
          <h2 className="text-caption text-muted-foreground uppercase">Buttons</h2>
          <div className="flex flex-wrap gap-3">
            <Button>Primary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="subtle">Subtle</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Danger</Button>
            <Button variant="link">Link</Button>
            <Button disabled>Disabled</Button>
          </div>
        </section>
        <section className="flex flex-col gap-3">
          <h2 className="text-caption text-muted-foreground uppercase">Surfaces & brand</h2>
          <div className="grid grid-cols-3 gap-4 sm:grid-cols-6">
            <Swatch label="background" className="bg-background" />
            <Swatch label="card + shadow" className="bg-card shadow-elevation-2" />
            <Swatch label="primary" className="bg-primary" />
            <Swatch label="violet-bright" className="bg-violet-bright" />
            <Swatch label="mint" className="bg-mint" />
            <Swatch label="tan" className="bg-tan" />
          </div>
        </section>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Временная заглушка экрана матрицы**

`frontend/src/screens/matrix/MatrixScreen.tsx` (заполнится в Task 9):

```tsx
export function MatrixScreen() {
  return <div className="p-8 text-foreground">Матрица (в разработке)</div>
}
```

- [ ] **Step 4: Создать роутер**

`frontend/src/router.tsx`:

```tsx
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router"
import { z } from "zod"

import { api } from "@/api/client"
import { DesignSystemShowcase } from "@/screens/DesignSystemShowcase"
import { MatrixScreen } from "@/screens/matrix/MatrixScreen"

const rootRoute = createRootRoute({ component: () => <Outlet /> })

const matrixSearchSchema = z.object({
  building_type_id: z.number().int().optional(),
  segment_id: z.number().int().optional(),
  q: z.string().optional(),
  offset: z.number().int().min(0).catch(0).default(0),
})

export const matrixRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: matrixSearchSchema,
  loaderDeps: ({ search }) => ({ building_type_id: search.building_type_id }),
  loader: async ({ deps }) => {
    // Дефолт типа объекта: невыразим в validateSearch (синхронный) — ставим тут,
    // после резолва /meta/building-types. Пустой список → без редиректа (пустое
    // состояние отрисует экран).
    if (deps.building_type_id === undefined) {
      const { data } = await api.GET("/meta/building-types")
      const first = data?.[0]
      if (first) {
        throw redirect({
          to: "/",
          search: (prev) => ({ ...prev, building_type_id: first.id }),
        })
      }
    }
  },
  component: MatrixScreen,
})

const designSystemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/design-system",
  component: DesignSystemShowcase,
})

// Экспортируем routeTree: интеграционный тест (Task 9) строит memory-router из
// ЭТОГО ЖЕ дерева, поэтому matrixRoute.useSearch()/useNavigate() в экране резолвятся
// строго (те же route-инстансы), без нестрогих вариантов.
export const routeTree = rootRoute.addChildren([matrixRoute, designSystemRoute])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
```

- [ ] **Step 5: Подключить роутер в `main.tsx`**

Замени `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"

import "./index.css"
import { router } from "@/router"
import { ThemeProvider } from "@/components/theme-provider.tsx"

const queryClient = new QueryClient()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>
)
```

- [ ] **Step 6: Удалить старый `App.tsx`**

Run: `cd frontend; git rm src/App.tsx`
(Содержимое перенесено в `DesignSystemShowcase`.)

- [ ] **Step 7: Проверить сборку/типы**

Run: `cd frontend; npm run typecheck; npm run build`
Expected: без ошибок (роутер типобезопасен, `App.tsx` больше не импортируется).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/router.tsx frontend/src/screens frontend/src/main.tsx frontend/package.json frontend/package-lock.json
git rm --cached src/App.tsx 2>/dev/null; git add -A frontend/src
git commit -m "feat(front): TanStack Router — маршруты / (матрица) и /design-system"
```

---

## Task 7: Данные (хуки Query) + MSW-обвязка тестов

**Files:**
- Install: `msw` (dev)
- Modify: `frontend/src/api/queries.ts`
- Create: `frontend/src/test/msw/handlers.ts`, `frontend/src/test/msw/server.ts`
- Modify: `frontend/src/test/setup.ts`

**Interfaces:**
- Produces: `useMatrix(params)`, `useBuildingTypes()`, `useSegments(buildingTypeId?)`; MSW `server` + дефолтные `handlers`.

- [ ] **Step 1: Установить MSW**

Run: `cd frontend; npm install -D msw@^2`

- [ ] **Step 2: Добавить хуки в `queries.ts`**

Дополни `frontend/src/api/queries.ts`:

```ts
// Сужаем data: openapi-fetch отдаёт data как T | undefined. После throw на error
// data всё ещё возможно-undefined по типу — гвардим, чтобы хук вернул T, а не
// T | undefined (иначе typecheck встанет на обращениях без ?.). См. Task 0 Step 3.
export function useMatrix(params: {
  building_type_id: number
  segment_id?: number
  q?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["matrix", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/listings/matrix", {
        params: { query: params },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /listings/matrix")
      return data
    },
  })
}

export function useBuildingTypes() {
  return useQuery({
    queryKey: ["building-types"],
    queryFn: async () => {
      const { data, error } = await api.GET("/meta/building-types")
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/building-types")
      return data
    },
  })
}

export function useSegments(buildingTypeId?: number) {
  return useQuery({
    queryKey: ["segments", buildingTypeId],
    enabled: buildingTypeId !== undefined,
    queryFn: async () => {
      const { data, error } = await api.GET("/meta/segments", {
        params: { query: { building_type_id: buildingTypeId } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/segments")
      return data
    },
  })
}
```

- [ ] **Step 3: MSW-хендлеры и сервер**

`frontend/src/test/msw/handlers.ts` (базовый жилой набор; тесты переопределяют по месту):

```ts
import { http, HttpResponse } from "msw"

const BASE = "/api"

export const buildingTypes = [
  { id: 1, code: "residential", name: "Жилые здания", sort_order: 1 },
  { id: 2, code: "office", name: "Офисные здания / ТРЦ", sort_order: 2 },
]

export const residentialSegments = [
  { id: 11, building_type_id: 1, group_id: null, name: "Бизнес", sort_order: 4 },
  { id: 12, building_type_id: 1, group_id: null, name: "Эконом", sort_order: 6 },
]

export const handlers = [
  http.get(`${BASE}/meta/building-types`, () => HttpResponse.json(buildingTypes)),
  http.get(`${BASE}/meta/segments`, () => HttpResponse.json(residentialSegments)),
  http.get(`${BASE}/listings/matrix`, () =>
    HttpResponse.json({
      columns: [
        { group: null, segments: [{ id: 11, name: "Бизнес", sort_order: 4 }] },
        { group: null, segments: [{ id: 12, name: "Эконом", sort_order: 6 }] },
      ],
      items: [
        {
          position_id: 100,
          position_name: "Насосы",
          category_path: "Оборудование / ОВиК",
          cells: [
            {
              segment_id: 11,
              vendors: [{ vendor_id: 5, name: "Grundfos", starred: true, ujin_integration: false, note: null }],
              spec_text: null,
              note: null,
            },
            { segment_id: 12, vendors: [], spec_text: "Россия", note: null },
          ],
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
  ),
]
```

`frontend/src/test/msw/server.ts`:

```ts
import { setupServer } from "msw/node"

import { handlers } from "./handlers"

export const server = setupServer(...handlers)
```

- [ ] **Step 4: Жизненный цикл MSW в `setup.ts`**

Замени `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach, beforeAll } from "vitest"

import { server } from "./msw/server"

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

- [ ] **Step 5: Проверить, что существующие тесты не сломались**

Run: `cd frontend; npm run test`
Expected: PASS (client/button/table/badge/card тесты зелёные; MSW не мешает — они не ходят в сеть).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/test frontend/package.json frontend/package-lock.json
git commit -m "feat(front): хуки useMatrix/useBuildingTypes/useSegments + MSW-обвязка тестов"
```

---

## Task 8: Чистые хелперы модели матрицы

Тестируемая без DOM логика: строки-заголовки разделов (дубль на границе страницы — намеренно) и поиск ячейки.

**Files:**
- Create: `frontend/src/screens/matrix/model.ts`, `frontend/src/screens/matrix/model.test.ts`

**Interfaces:**
- Consumes: типы `components["schemas"]["MatrixRow"]`/`MatrixCell` из `@/api/schema`.
- Produces: `withSectionHeaders(items): DisplayRow[]`, `cellFor(row, segmentId): MatrixCell | null`, тип `DisplayRow`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/screens/matrix/model.test.ts`:

```ts
import { describe, expect, it } from "vitest"

import type { components } from "@/api/schema"

import { cellFor, withSectionHeaders } from "./model"

type MatrixRow = components["schemas"]["MatrixRow"]

const row = (position_id: number, category_path: string): MatrixRow => ({
  position_id,
  position_name: `p${position_id}`,
  category_path,
  cells: [{ segment_id: 11, vendors: [], spec_text: "Россия", note: null }],
})

describe("withSectionHeaders", () => {
  it("вставляет заголовок на смене category_path", () => {
    const out = withSectionHeaders([row(1, "A"), row(2, "A"), row(3, "B")])
    const kinds = out.map((r) => r.kind)
    expect(kinds).toEqual(["section", "position", "position", "section", "position"])
  })

  it("печатает заголовок на первой строке страницы, даже если раздел продолжается (дубль на границе — намеренно)", () => {
    // Страница N+1 начинается с продолжения раздела 'A' — заголовок ДОЛЖЕН быть.
    const out = withSectionHeaders([row(4, "A"), row(5, "A")])
    expect(out[0].kind).toBe("section")
    expect(out[0].kind === "section" && out[0].categoryPath).toBe("A")
  })
})

describe("cellFor", () => {
  it("находит ячейку по segment_id, иначе null", () => {
    const r = row(1, "A")
    expect(cellFor(r, 11)?.spec_text).toBe("Россия")
    expect(cellFor(r, 999)).toBeNull()
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/screens/matrix/model.test.ts`
Expected: FAIL (модуль не найден).

- [ ] **Step 3: Реализовать `model.ts`**

`frontend/src/screens/matrix/model.ts`:

```ts
import type { components } from "@/api/schema"

export type MatrixRow = components["schemas"]["MatrixRow"]
export type MatrixCell = components["schemas"]["MatrixCell"]

export type DisplayRow =
  | { kind: "section"; categoryPath: string; key: string }
  | { kind: "position"; row: MatrixRow; key: string }

/**
 * Разворачивает страницу позиций в строки отображения, вставляя строку-заголовок
 * раздела на смене category_path. prev сбрасывается на каждый вызов (на страницу),
 * поэтому раздел, продолжающийся с прошлой страницы, печатает заголовок на первой
 * строке новой — это намеренно (контекст на новой странице), НЕ баг.
 */
export function withSectionHeaders(items: MatrixRow[]): DisplayRow[] {
  const out: DisplayRow[] = []
  let prev: string | null = null
  for (const row of items) {
    if (row.category_path !== prev) {
      out.push({ kind: "section", categoryPath: row.category_path, key: `sec:${row.category_path}` })
      prev = row.category_path
    }
    out.push({ kind: "position", row, key: `pos:${row.position_id}` })
  }
  return out
}

export function cellFor(row: MatrixRow, segmentId: number): MatrixCell | null {
  return row.cells.find((c) => c.segment_id === segmentId) ?? null
}
```

- [ ] **Step 4: Запустить — проходит**

Run: `cd frontend; npx vitest run src/screens/matrix/model.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/matrix/model.ts frontend/src/screens/matrix/model.test.ts
git commit -m "feat(matrix): чистые хелперы модели (withSectionHeaders, cellFor)"
```

---

## Task 9: Экран матрицы + рендер ячейки + интеграционный тест

Собираем экран: фильтры (тип объекта/класс/поиск в URL), группы колонок (TanStack Table), строки-заголовки разделов, ячейки, серверная пагинация. MSW-интеграция.

**Files:**
- Create: `frontend/src/screens/matrix/columns.tsx`
- Modify: `frontend/src/screens/matrix/MatrixScreen.tsx` (заменяет заглушку)
- Create: `frontend/src/screens/matrix/MatrixScreen.test.tsx`

**Interfaces:**
- Consumes: `useMatrix`/`useBuildingTypes`/`useSegments` (Task 7), `withSectionHeaders`/`cellFor` (Task 8), DS `Table`/`Badge`/`Card` (Tasks 3–5), `matrixRoute` (Task 6), TanStack Table.
- Produces: рабочий `MatrixScreen`.

- [ ] **Step 1: Рендер ячейки и колонок**

`frontend/src/screens/matrix/columns.tsx`:

```tsx
import { createColumnHelper, type ColumnDef } from "@tanstack/react-table"
import { Star } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { components } from "@/api/schema"

import { cellFor, type MatrixCell, type MatrixRow } from "./model"

type MatrixColumnGroup = components["schemas"]["MatrixColumnGroup"]

export function renderCell(cell: MatrixCell | null) {
  if (!cell) return <span className="text-muted-foreground">—</span>
  if (cell.vendors.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {cell.vendors.map((v) => (
          <Badge key={v.vendor_id} variant="outline" title={v.note ?? undefined}>
            {v.starred && <Star className="size-3 fill-current" aria-label="действующее соглашение" />}
            {v.name}
            {v.ujin_integration && <span className="text-caption text-muted-foreground">Ujin</span>}
          </Badge>
        ))}
      </div>
    )
  }
  if (cell.spec_text) return <Badge variant="requirement">{cell.spec_text}</Badge>
  return <span className="text-muted-foreground">—</span>
}

const ch = createColumnHelper<MatrixRow>()

export function buildColumnDefs(columns: MatrixColumnGroup[]): ColumnDef<MatrixRow, unknown>[] {
  const positionCol = ch.display({
    id: "position",
    header: "Позиция",
    cell: ({ row }) => <span className="font-medium">{row.original.position_name}</span>,
  }) as ColumnDef<MatrixRow, unknown>

  const segCols = columns.flatMap((grp) => {
    const leaves = grp.segments.map(
      (s) =>
        ch.display({
          id: String(s.id),
          header: s.name,
          cell: ({ row }) => renderCell(cellFor(row.original, s.id)),
        }) as ColumnDef<MatrixRow, unknown>
    )
    if (!grp.group) return leaves
    return [
      ch.group({ id: `g${grp.group.id}`, header: grp.group.name, columns: leaves }) as ColumnDef<
        MatrixRow,
        unknown
      >,
    ]
  })

  return [positionCol, ...segCols]
}
```

- [ ] **Step 2: Написать интеграционный тест (MSW)**

`frontend/src/screens/matrix/MatrixScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

// Переиспользуем БОЕВОЕ дерево маршрутов — те же route-инстансы, что импортирует
// экран, поэтому строгие matrixRoute.useSearch()/useNavigate() резолвятся в тесте.
import { routeTree } from "@/router"
import { server } from "@/test/msw/server"

function makeRouter(initial = "/?building_type_id=1") {
  return createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
}

function renderWith(router: ReturnType<typeof makeRouter>) {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe("MatrixScreen", () => {
  it("рисует групповые шапки, вендора со звездой, требование и заголовок раздела", async () => {
    renderWith(makeRouter())
    expect(await screen.findByText("Насосы")).toBeInTheDocument()
    expect(screen.getByText("Grundfos")).toBeInTheDocument()
    expect(screen.getByLabelText("действующее соглашение")).toBeInTheDocument()
    expect(screen.getByText("Россия")).toBeInTheDocument()
    expect(screen.getByText("Оборудование / ОВиК")).toBeInTheDocument() // заголовок раздела
    expect(screen.getByText("Бизнес")).toBeInTheDocument() // шапки классов
    expect(screen.getByText("Эконом")).toBeInTheDocument()
  })

  it("серверная пагинация: клик «Вперёд» увеличивает offset в URL на PAGE_SIZE", async () => {
    server.use(
      http.get("/api/listings/matrix", () =>
        HttpResponse.json({
          columns: [{ group: null, segments: [{ id: 11, name: "Бизнес", sort_order: 4 }] }],
          items: [
            {
              position_id: 100,
              position_name: "Насосы",
              category_path: "Оборудование / ОВиК",
              cells: [{ segment_id: 11, vendors: [], spec_text: "Россия", note: null }],
            },
          ],
          total: 120, // > PAGE_SIZE ⇒ «Вперёд» активна
          limit: 50,
          offset: 0,
        })
      )
    )
    const router = makeRouter()
    renderWith(router)
    await screen.findByText("Насосы")
    await userEvent.click(screen.getByRole("button", { name: "Вперёд" }))
    await waitFor(() => expect(router.state.location.search).toMatchObject({ offset: 50 }))
  })
})
```

- [ ] **Step 3: Запустить — падает**

Run: `cd frontend; npx vitest run src/screens/matrix/MatrixScreen.test.tsx`
Expected: FAIL (MatrixScreen — заглушка).

- [ ] **Step 4: Реализовать экран**

Замени `frontend/src/screens/matrix/MatrixScreen.tsx`:

```tsx
import { getCoreRowModel, useReactTable, flexRender } from "@tanstack/react-table"
import { useMemo } from "react"

import { matrixRoute } from "@/router"
import { useMatrix, useBuildingTypes, useSegments } from "@/api/queries"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"

import { buildColumnDefs } from "./columns"
import { withSectionHeaders } from "./model"

const PAGE_SIZE = 50 // единый источник: limit запроса и шаг пагинатора (не хардкодить дважды)

export function MatrixScreen() {
  const search = matrixRoute.useSearch()
  const navigate = matrixRoute.useNavigate()

  const buildingTypes = useBuildingTypes()
  const segments = useSegments(search.building_type_id)

  const matrix = useMatrix({
    building_type_id: search.building_type_id ?? 0,
    segment_id: search.segment_id,
    q: search.q || undefined,
    limit: PAGE_SIZE,
    offset: search.offset,
  })

  const columns = useMemo(
    () => buildColumnDefs(matrix.data?.columns ?? []),
    [matrix.data?.columns]
  )
  const table = useReactTable({
    data: matrix.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  })
  const leafCount = table.getAllLeafColumns().length

  // Пустое состояние: типов объектов нет (свежая БД) — не падаем.
  if (buildingTypes.data && buildingTypes.data.length === 0) {
    return <div className="p-8 text-muted-foreground">Типы объектов не заведены.</div>
  }

  const displayRows = withSectionHeaders(matrix.data?.items ?? [])

  return (
    <div className="flex flex-col gap-4 p-6 text-foreground">
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Тип объекта
            <select
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              value={search.building_type_id ?? ""}
              onChange={(e) =>
                navigate({
                  search: (p) => ({
                    ...p,
                    building_type_id: Number(e.target.value),
                    segment_id: undefined,
                    offset: 0,
                  }),
                })
              }
            >
              {buildingTypes.data?.map((bt) => (
                <option key={bt.id} value={bt.id}>
                  {bt.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Класс
            <select
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              value={search.segment_id ?? ""}
              onChange={(e) =>
                navigate({
                  search: (p) => ({
                    ...p,
                    segment_id: e.target.value ? Number(e.target.value) : undefined,
                    offset: 0,
                  }),
                })
              }
            >
              <option value="">Все классы</option>
              {segments.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Поиск
            <input
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              defaultValue={search.q ?? ""}
              placeholder="позиция / вендор / раздел"
              onChange={(e) => {
                const val = e.target.value
                navigate({ search: (p) => ({ ...p, q: val || undefined, offset: 0 }) })
              }}
            />
          </label>
        </CardContent>
      </Card>

      {matrix.isError && (
        <div className="text-destructive">Ошибка загрузки матрицы.</div>
      )}

      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id} colSpan={h.colSpan}>
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {displayRows.map((dr) =>
            dr.kind === "section" ? (
              <TableRow key={dr.key} className="bg-muted/40">
                <TableCell colSpan={leafCount} className="text-caption font-medium text-muted-foreground">
                  {dr.categoryPath}
                </TableCell>
              </TableRow>
            ) : (
              <TableRow key={dr.key}>
                {table
                  .getRowModel()
                  .rows.find((r) => r.original.position_id === dr.row.position_id)
                  ?.getVisibleCells()
                  .map((c) => (
                    <TableCell key={c.id}>{flexRender(c.column.columnDef.cell, c.getContext())}</TableCell>
                  ))}
              </TableRow>
            )
          )}
        </TableBody>
      </Table>

      <div className="flex items-center gap-3 text-caption text-muted-foreground">
        <span>
          {search.segment_id ? "Позиций в классе" : "Позиций"}: {matrix.data?.total ?? 0}
        </span>
        <Button
          variant="outline"
          disabled={search.offset === 0}
          onClick={() => navigate({ search: (p) => ({ ...p, offset: Math.max(0, p.offset - PAGE_SIZE) }) })}
        >
          Назад
        </Button>
        <Button
          variant="outline"
          disabled={(matrix.data?.offset ?? 0) + PAGE_SIZE >= (matrix.data?.total ?? 0)}
          onClick={() => navigate({ search: (p) => ({ ...p, offset: p.offset + PAGE_SIZE }) })}
        >
          Вперёд
        </Button>
      </div>
    </div>
  )
}
```

> **Примечание для реализатора:** строгие `matrixRoute.useSearch()`/`useNavigate()` работают и в тесте, потому что тест (Step 2) строит memory-router из БОЕВОГО `routeTree` (те же route-инстансы). Не подменяй их нестрогими `{ strict: false }` — это сломает типизацию search без нужды. Экран зависит от `matrixRoute` из `@/router`, тест — от `routeTree` оттуда же; расхождения роутеров нет.

- [ ] **Step 5: Запустить интеграционный тест**

Run: `cd frontend; npx vitest run src/screens/matrix/MatrixScreen.test.tsx`
Expected: PASS (MSW отдаёт дефолтный payload; звезда, требование, шапки, заголовок раздела на месте).

- [ ] **Step 6: Проверить типы**

Run: `cd frontend; npm run typecheck`
Expected: без ошибок.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/screens/matrix/columns.tsx frontend/src/screens/matrix/MatrixScreen.tsx frontend/src/screens/matrix/MatrixScreen.test.tsx
git commit -m "feat(matrix): экран матрицы — фильтры, группы колонок, дерево-заголовки, ячейки, пагинация"
```

---

## Task 10: Финал — `just ci`, devlog, TECH_DEBT

**Files:**
- Modify: `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-09-listing-matrix.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли` (types → lint → typecheck → test; db-тесты идут на тест-ветке Neon либо скипаются локально). Чинить всё красное до зелёного.

- [ ] **Step 2: Снять «Каталог компонентов» из TECH_DEBT и добавить заметки**

В `docs/TECH_DEBT.md`, секция «Дизайн-система (foundation)» → «Компоненты»: удали пункт «**Каталог компонентов.** Следующий срез …» (закрыт: `table`/`badge`/`card` собраны). В конец файла (перед «## Прочее» или отдельной секцией «## Матрица перечня») добавь:

```markdown
## Матрица перечня

Внесено при реализации матрицы (ветка `feat/listing-matrix`). Источник:
[спека](superpowers/specs/2026-07-09-listing-matrix-design.md), [план](superpowers/plans/2026-07-09-listing-matrix.md).

- **Сворачиваемое дерево разделов.** v1 показывает плоские строки-заголовки по
  `category_path`; сворачиваемые узлы конфликтуют с серверной пагинацией — отложено.
- **Рекурсивные `category_path`/`category_sort_path`.** v1 сводит вызовы к
  O(различные категории на странице) через CTE `cats`. Материализация пути (доп.
  колонка на `category` с триггерным пересчётом / materialized view) понадобится,
  если категории окажутся почти уникальны per-position или дерево сильно вырастет.
- **Подсветка совпавших ячеек при поиске.** `q` по `vendor_name` отбирает позицию
  целиком, ячейки с совпадением не подсвечиваются (v1).
- **Дебаунс поиска.** Поле поиска пишет в URL на каждый ввод; вынести дебаунс, если
  начнёт частить перезапросами.
- **Групповая шапка над одной колонкой.** При сужении `segment_id` до класса,
  входящего в группу (офис), `_group_columns` вернёт группу из одного сегмента —
  групповая шапка над единственной колонкой. Косметика; схлопнуть при полировке.
```

- [ ] **Step 3: Написать devlog**

`docs/devlog/2026-07-09-listing-matrix.md` — по шаблону соседних записей: цель, что сделано (server pivot `/listings/matrix`, `category_sort_path`, DS `table/badge/card`, TanStack Router, экран), развилки (ссылка на спеку r5), находки, что отложено (TECH_DEBT), команды проверки.

- [ ] **Step 4: Commit (docs-only — `just ci` не требуется, но уже прогнан)**

```bash
git add docs/TECH_DEBT.md docs/devlog/2026-07-09-listing-matrix.md
git commit -m "docs(matrix): devlog + закрытие каталога компонентов в TECH_DEBT"
```

- [ ] **Step 5: PR**

```bash
git push -u origin feat/listing-matrix
gh pr create --base main --title "feat: матрица перечня (первый продуктовый экран)" --body "Реализует §4.1 ТЗ по [спеке](docs/superpowers/specs/2026-07-09-listing-matrix-design.md) r5 и [плану](docs/superpowers/plans/2026-07-09-listing-matrix.md). Server pivot /listings/matrix, category_sort_path, DS table/badge/card, TanStack Router, экран матрицы. just ci зелёный."
```

---

## Self-Review

**1. Spec coverage:**
- §Контракт (Matrix*, params) → Task 2. ✔
- §Выборка (CTE `pos_page`/`cats`, `DISTINCT position_id`, шаг ячеек без `q`) → Task 2 Step 4. ✔
- §Миграция `category_sort_path` (пары `[sort_order, id]`) → Task 1. ✔
- §Группировка колонок (payload → `columnHelper.group`) → Task 2 (`_group_columns`), Task 9 (`buildColumnDefs`). ✔
- §Дерево строк (плоские заголовки, дубль на границе) → Task 8 (`withSectionHeaders`), Task 9 (рендер). ✔
- §Роутинг (TanStack Router, дефолт в loader'е, пустой список) → Task 6. ✔
- §Срез компонентов (`table`/`badge`/`card` только) → Tasks 3–5. ✔
- §Семантика `q` + стык `q`×`segment_id` → Task 2 db-тесты (`test_q_with_segment_id_excludes_empty_in_class`). ✔
- §Подпись `total` при сужении → Task 9 (тернарник «Позиций в классе»). ✔
- §Тесты (звезда как есть, группировка, `total`, пустая ячейка отсутствует) → Task 2 db-тесты; фронт-кейсы (рендер, звезда, требование, заголовок раздела, **серверная пагинация — клик «Вперёд» → offset в URL**) → Tasks 8–9. ✔
- §Вне объёма (нет мутаций/светофора/Excel) → соблюдено; экран read-only. ✔

**2. Placeholder scan:** Заглушка `MatrixScreen` в Task 6 намеренная и заменяется в Task 9 (не плейсхолдер-в-финале). Кода без тела нет.

**3. Type consistency:** `MatrixRow`/`MatrixCell` — из `components["schemas"]` (единый источник после `just types`); хелперы `withSectionHeaders`/`cellFor` (Task 8) и `buildColumnDefs`/`renderCell` (Task 9) используют те же типы. `_group_columns` (Task 2) и `buildColumnDefs` (Task 9) согласованы по форме `MatrixColumnGroup{group, segments}`. Хуки `useMatrix`/`useBuildingTypes`/`useSegments` (Task 7) потребляются экраном (Task 9) с теми же именами.

**Замечание по рискам реализации:**
- **Task 0 Preflight обязателен** — три сверки с кодом (сигнатура `category_path` = id категории; `baseUrl` = `/api`; `undefined`-политика openapi-fetch). Все три подтверждены при написании плана; Task 0 ловит, если репо поехал.
- `= ANY(:pos_ids)` со списком под asyncpg — если драйвер не примет, заменить на `IN :pos_ids` с `bindparam("pos_ids", expanding=True)` (guard на непустой список уже есть). db-тест Task 2 это ловит.
- Строгий/тестовый роутер — **снято**: тест переиспользует боевой `routeTree` (Task 6 экспортирует его), строгие `useSearch`/`useNavigate` резолвятся без нестрогих вариантов.
