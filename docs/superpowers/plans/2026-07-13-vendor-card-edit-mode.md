# Режим правки карточки вендора + типографика v3 «Где разрешён» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Отделить чтение от правки на карточке вендора (view ↔ edit), дать редактирование разрешений (исключить/добавить вендора по классу/позиции/стандарту через мутации живого `listing`) и довести блок «Где разрешён» до типографики v3.

**Architecture:** Бэкенд получает net-new пишущий контур (ревизия `0006` — функция `ensure_open_release`; listing-мутации add/exclude/restore + `PATCH kind` + `GET /meta/positions`), нейтральный к экрану (ту же ячейку однажды правит матрица). Правки идут **прямо в живой `listing`** (у `listing` нет `release_id`); открытый `release` — лишь маркер «есть неопубликованные изменения». Обратимость держится на «вернуть» (un-delete-first-else-INSERT) и неизменяемости published-релизов. Фронт: `editMode` — локальный state экрана, все affordance гейтятся им; типографика v3 и edit-слой ложатся на существующий кастомный Radix-триггер аккордеона; чистые хелперы (`splitQualifier`, счётчики масштаба) — в `model.ts`.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy Core (async, asyncpg), PostgreSQL, Alembic (чистый SQL); Vite + React + TS, shadcn/ui + Tailwind (токены), TanStack Router/Query, radix-ui, vitest + MSW.

Спека: [docs/superpowers/specs/2026-07-13-vendor-card-edit-mode-design.md](../specs/2026-07-13-vendor-card-edit-mode-design.md).

## Global Constraints

Каждая задача неявно наследует (CLAUDE.md «Золотые правила» + решения спеки):

- **Schema-first, без ORM.** Только SQLAlchemy Core (`text(...)`), значения — bind-параметрами, не конкатенацией.
- **Инвариант — в БД (golden-rule #6).** Единственность открытого маркера, soft-delete, «ячейка = вендоры ЛИБО мета» — держат ограничения/триггеры `0001`. Мутации их только вызывают; правило-логику НЕ дублируем на фронте.
- **Две базовые миграции неизменны (golden-rule #5).** Новое — ТОЛЬКО новой ревизией чистым SQL через `op.execute` (`just makemigration name="..."`). autogenerate не используем.
- **Пишущие эндпоинты — только `Depends(tx)` + `Depends(require_admin)`.** `tx` первым делом ставит `app.user` через `set_config(..., true)` ([db.py:60-73](../../../backend/app/db.py)); аудит подписывается верным логином. Роли — в API (golden-rule #4).
- **Накат ревизии 0006 — и на боевую, и на тест-ветку.** `just migrate` (боевая) **и** `just migrate-test` (тест-ветка Neon). Память проекта: миграция только на тест-ветке молча падает 500 в живом приложении.
- **Только семантические токены DS. Новых токенов НЕ заводить.** Акцент сводки «все классы» → `text-success` / `--ds-state-success` (mint, единственный цвет блока); баннер режима → subtle-violet (существующий акцент); sunken-полоса → `bg-muted`; делители → `border-border`/`border-border/60`; пунктир → `border-dashed border-border-strong`; фокус → `--ring`; destructive kebab → токен `destructive`.
- **DS `components/ui/accordion.tsx` НЕ форкаем.** Кастомный триггер — на `AccordionPrimitive.Trigger` из `radix-ui` (как уже в `VendorCardScreen.tsx`), состояние через `group-data-[state=open]`.
- **UI только на русском.** Идентификаторы/код — по-английски.
- **Типы сквозные:** после правки бэкенд-контракта — `just types` (регенерит `frontend/src/api/schema.d.ts`, **gitignored** — не коммитим).
- **Фронт-задачи:** `npm run format` + `npm run format:check` ПЕРЕД коммитом (не только vitest/typecheck).
- **db-тесты (маркер `db`)** идут на тест-ветке Neon; без `DATABASE_URL_TEST` скипаются (локальный `just ci` остаётся зелёным). Изоляция — откат транзакции. Новая функция `ensure_open_release` — **обычный TDD** (логика НОВАЯ: тест FAIL до наката 0006 на тест-ветку, инвертированный TDD тут не применяем).
- **Одна ветка, один PR в конце.** Ветка `feat/vendor-card-edit-mode` от актуального `main` (предшественники PR #20/#21/#22 влиты, стекинга нет). Коммит на задачу, финальный `just ci` зелёный, PR в `main` — в Task 7. `main` держим зелёным.

### Решено заказчиком (в спеке было «открыто» — здесь ЗАКРЫТО, не переоткрывать)

1. **`other` → «прочее».** `KIND_LABELS` ([model.ts:3-7](../../../frontend/src/screens/vendors/model.ts)) **не меняем** — там уже «прочее», и оно уже в бейдже. Дропдаун `kind` **читает `KIND_LABELS` как есть** → бейдж и опция совпадают по построению (одна константа, ноль дрейфа). Выбор спеки «другое» отменён. Диффа к константе нет.
2. **Исключение = ОДИН scoped-эндпоинт** `POST /vendors/{id}/listings/exclude` с телом `{scope, position_id?, segment_id?, building_type_id?}` (не три ручки). Причина: масштаб (`excluded_positions/classes`) отдаётся из одного места; три ручки = три копии идентичной tx-обвязки (`tx` + soft-delete по WHERE + `ensure_open_release` при rowcount>0); валидация по scope — тривиальный pydantic-дискриминатор; будущая редактируемая матрица предпочтёт один вызов.
3. **Масштаб N/M — двухфазно, без preview-эндпоинта.** Для диалога подтверждения фронт считает N/M **из уже загруженного дерева `where-allowed`** (данные на экране, диалог мгновенный). Ответ мутации возвращает **фактический** масштаб (`{excluded_positions, excluded_classes}` через `RETURNING`/агрегат в той же транзакции) — он идёт в тост и является истиной, если гонка разошлась с клиентской оценкой. **Preview = клиент, факт = сервер, отдельного preview-эндпоинта нет.**
4. **Инвалидация алиасов — `["matrix"]` НЕ добавляем.** Матрица показывает `vendor.name`, алиасов в её payload нет (alias = сущность поиска/справки). `useAddAlias`/`useRemoveAlias` продолжают гасить только `["vendor", id]` — **эти хуки не трогаем** (закрывает открытый вопрос #3 спеки).
5. **`label` авто-open-релиза — НЕЙТРАЛЬНЫЙ, не ложь.** Проверенный факт: `freeze_release` **не перезаписывает** `label` (только `status='published'`, `frozen_at=now()`, `author=coalesce(...)` — [0001:396-400](../../../backend/migrations/sql/0001_core_schema.sql)). Значит авто-label вроде «… — черновик» доехал бы до published-релиза и врал. `ensure_open_release` ставит **«`<тип> — рабочая версия`»** — не утверждает ничего ложного; поле `release.label` остаётся редактируемым, человек уточнит его при публикации (экран изданий, §5 — отдельная будущая забота, НЕ этот срез). **`freeze_release` в этом срезе НЕ трогаем.**

---

## Файловая структура

**Бэкенд — изменить:**
- Create: `backend/migrations/versions/0006_ensure_open_release.py` — функция `ensure_open_release(int)`.
- Modify: `backend/app/schemas/__init__.py` — `VendorHeaderUpdate.kind`; `ListingAdd`/`ListingExclude`/`ListingRestore`/`ListingExcludeResult`; `MetaPosition`.
- Modify: `backend/app/routers/vendors.py` — `_is_cell_chk` хелпер; `add_listings`/`exclude_listings`/`restore_listing`; ветка `kind` в `update_vendor_header`.
- Modify: `backend/app/routers/meta.py` — `GET /meta/positions`.
- Create: `backend/tests/db/test_ensure_open_release.py` — db-тесты функции.
- Modify: `backend/tests/api/test_vendors.py` — api-тесты мутаций + RBAC.
- Modify/Create: `backend/tests/api/test_meta.py` — тест `/meta/positions`.

**Фронт — изменить:**
- Modify: `frontend/src/screens/vendors/model.ts` — `splitQualifier`; `excludeScaleForPosition`/`excludeScaleForStandard`; `pluralClasses`; переписать `excludedTooltip`/`whereAllowedLegend`.
- Modify: `frontend/src/screens/vendors/model.test.ts` — юниты новых хелперов.
- Modify: `frontend/src/screens/vendors/InlineEditText.tsx` — проп `readOnly`.
- Modify: `frontend/src/api/queries.ts` — `useUpdateVendorHeader` (+`kind`); `useAddListings`/`useExcludeListings`/`useRestoreListing` (гасят 4 ключа).
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx` — `editMode`/`expanded`; тумблер + баннер; гейтинг affordance; типографика v3; операции классов/позиций/стандартов.
- Create: `frontend/src/screens/vendors/ExcludeDialog.tsx` — диалог масштаба (позиция/стандарт).
- Create: `frontend/src/screens/vendors/AddStandardDialog.tsx` — диалог «+ стандарт» (три шага).
- Create: `frontend/src/components/ui/{dialog,popover,command,checkbox,radio-group}.tsx` — 5 стоковых shadcn-примитивов.
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx` — тексты v3, view/edit, операции; **обновить существующие тесты под view-default**.
- Modify: `frontend/src/test/msw/handlers.ts` — хендлеры новых мутаций/`/meta/positions`.

**Доки (Task 7):** `CLAUDE.md`, `docs/TECH_DEBT.md`, `docs/devlog/2026-07-13-vendor-card-edit-mode.md`.

---

## Task 1: Бэкенд — ревизия 0006 `ensure_open_release` (маркер открытого релиза)

**Files:**
- Create: `backend/migrations/versions/0006_ensure_open_release.py`
- Test: `backend/tests/db/test_ensure_open_release.py`

**Interfaces:**
- Consumes: `release` (`uq_release_one_open ON (building_type_id) WHERE status='open'`, [0001:320-321](../../../backend/migrations/sql/0001_core_schema.sql)), `building_type`; фабрика `make_building_type` ([factories.py:187](../../../backend/tests/factories.py)), фикстура `db_conn`.
- Produces: SQL-функция `ensure_open_release(p_bt int) RETURNS int` — возвращает id открытого маркера (создаёт, если нет; иначе переиспользует). Вызывается всеми listing-мутациями Task 2.

- [ ] **Step 1: Написать db-тест (обычный TDD — логика новая)**

Create `backend/tests/db/test_ensure_open_release.py`:

```python
"""ensure_open_release (ревизия 0006): единственный открытый маркер на тип объекта.

Обычный TDD: функция НОВАЯ, до наката 0006 на тест-ветку тест падает.
Настоящую параллельность в pytest не воспроизвести — проверяем идемпотентность
и ветку ON CONFLICT (повторный вызов переиспользует существующий id).
"""

import pytest
from sqlalchemy import text

from tests import factories as f

pytestmark = pytest.mark.db


async def _open_count(db_conn, bt: int) -> int:
    return (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one()


async def test_ensure_open_release_creates_when_absent(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="eor-create", name="ЖК-тест")
    rid = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    assert rid is not None
    assert await _open_count(db_conn, bt) == 1
    row = (
        await db_conn.execute(
            text("SELECT label, status FROM release WHERE id = :id"), {"id": rid}
        )
    ).mappings().one()
    assert row["status"] == "open"
    assert row["label"].strip() != ""  # NOT NULL, нейтральный непустой текст
    assert "рабочая версия" in row["label"]


async def test_ensure_open_release_idempotent_reuse(db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="eor-reuse", name="Офис-тест")
    first = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    second = (
        await db_conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    ).scalar_one()
    assert first == second  # ветка ON CONFLICT → переиспользован тот же маркер
    assert await _open_count(db_conn, bt) == 1  # второго открытого не появилось
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd backend; uv run pytest tests/db/test_ensure_open_release.py -v`
Expected: FAIL (`function ensure_open_release(integer) does not exist`), либо SKIP без `DATABASE_URL_TEST`. Если SKIP — временно проверить локально с тест-URL или довериться CI.

- [ ] **Step 3: Создать ревизию**

Run: `just makemigration name="ensure_open_release"` — создаст пустой файл в `versions/`. Переименовать/заполнить как `0006_ensure_open_release.py`:

```python
"""Ревизия №6: ensure_open_release(building_type_id) — маркер открытого релиза.

Автосоздание «черновика» = обеспечение ЕДИНСТВЕННОГО open-маркера на тип объекта
(симметрия с freeze_release; инвариант в БД — CLAUDE.md #6). Гонка снимается
ограничением uq_release_one_open (0001), не сервисным локом: параллельные вызовы
конфликтуют по частичному уникальному индексу, проигравший переиспользует чужой id.

label — НЕЙТРАЛЬНЫЙ и не ложь: freeze_release НЕ перезаписывает label (0001:396-400),
значит любой авто-label доедет до published-релиза как есть. «<тип> — рабочая версия»
не утверждает ничего ложного; человек уточнит его при публикации (экран изданий, §5).

Revision ID: 0006_ensure_open_release
Revises: 0005_vendor_where_allowed
"""

from __future__ import annotations

from alembic import op

revision = "0006_ensure_open_release"
down_revision = "0005_vendor_where_allowed"
branch_labels = None
depends_on = None

_UP = """
CREATE FUNCTION ensure_open_release(p_bt int) RETURNS int LANGUAGE plpgsql AS
$fn$
DECLARE v_id int;
BEGIN
    INSERT INTO release (building_type_id, label, status)
    VALUES (p_bt,
            (SELECT name || ' — рабочая версия' FROM building_type WHERE id = p_bt),
            'open')
    ON CONFLICT (building_type_id) WHERE status = 'open' DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN            -- открытый маркер уже был (повтор/гонка)
        SELECT id INTO v_id FROM release
        WHERE building_type_id = p_bt AND status = 'open';
    END IF;
    RETURN v_id;
END;
$fn$;
"""

_DOWN = "DROP FUNCTION IF EXISTS ensure_open_release(int);"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
```

> `ON CONFLICT (building_type_id) WHERE status = 'open'` — таргетинг на **частичный** уникальный индекс `uq_release_one_open`; предикат `WHERE` обязателен, чтобы Postgres сопоставил именно этот индекс. При конфликте `DO NOTHING` → строка не возвращается → `v_id` остаётся `NULL` (в plpgsql `INTO` без STRICT не ошибка) → добираем существующий id вторым `SELECT`.

- [ ] **Step 4: Накатить на тест-ветку и боевую**

Run: `just migrate-test` — Expected: применит `0006` на тест-ветку Neon.
Run: `just migrate` — Expected: применит `0006` на боевую (иначе фича молча 500 в живом приложении — память проекта).
Sanity: `just migrate-current` — Expected: head = `0006_ensure_open_release`.

- [ ] **Step 5: Прогнать — PASS**

Run: `cd backend; uv run pytest tests/db/test_ensure_open_release.py -v`
Expected: PASS (обе ветки — create + idempotent-reuse).

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0006_ensure_open_release.py backend/tests/db/test_ensure_open_release.py
git commit -m "feat(db): ревизия 0006 ensure_open_release — маркер открытого релиза (O2)"
```

---

## Task 2: Бэкенд — listing-мутации + `PATCH kind` + `/meta/positions`

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/vendors.py`
- Modify: `backend/app/routers/meta.py`
- Test: `backend/tests/api/test_vendors.py`
- Test: `backend/tests/api/test_meta.py`

**Interfaces:**
- Consumes: `ensure_open_release` (Task 1); `tx`/`require_admin`; фабрики `make_building_type`/`make_segment`/`make_category`/`make_position`/`make_vendor`/`make_listing` ([factories.py](../../../backend/tests/factories.py)); фикстуры `client`/`as_admin`/`as_viewer`/`db_conn` ([conftest.py](../../../backend/tests/conftest.py)).
- Produces:
  - `POST /vendors/{id}/listings` `{position_id:int, segment_ids:int[]}` → 204. Un-delete-first-else-INSERT `allowed` по каждому классу (idempotent). Общий для «+ класс»/«+ позиция»/«+ стандарт».
  - `POST /vendors/{id}/listings/exclude` `{scope, position_id?, segment_id?, building_type_id?}` → `ListingExcludeResult{excluded_positions:int, excluded_classes:int}`.
  - `POST /vendors/{id}/listings/restore` `{position_id:int, segment_id:int}` → 204.
  - `PATCH /vendors/{id}` принимает `+kind`.
  - `GET /meta/positions?building_type_id=&q=` → `MetaPosition[]{id,name,category_path}`.

### Как из listing-строки достаётся building_type (проверенный факт)

`building_type` достижим **только через `segment.building_type_id`** ([0001:56-66](../../../backend/migrations/sql/0001_core_schema.sql)), НЕ через `position` (позиции привязаны к общему для всех типов дереву `category`, [0001:78-86](../../../backend/migrations/sql/0001_core_schema.sql)). Отсюда:
- **class** (`position_id`+`segment_id`): `bt = (SELECT building_type_id FROM segment WHERE id = :segment_id)`. WHERE точный, `bt` нужен только для `ensure_open_release`.
- **position** (`position_id`+`building_type_id`): `bt` из тела (позиция может жить в нескольких типах через разные сегменты — исключаем только классы ЭТОГО типа).
- **standard** (`building_type_id`): `bt` из тела.

### Трансляция триггера `listing_cell_chk` → 409 (проверенный факт)

`listing_cell_chk` — это `RAISE EXCEPTION` в plpgsql ([0001:205-242](../../../backend/migrations/sql/0001_core_schema.sql)), **не** нарушение ограничения. asyncpg отдаёт его как `RaiseError` (SQLSTATE **`P0001`**), SQLAlchemy оборачивает в `DBAPIError` — это **НЕ `IntegrityError`**. Ловим `DBAPIError` и проверяем `sqlstate`. Soft-delete (exclude) триггер НЕ ограничивает (при `deleted_at IS NOT NULL` он сразу `RETURN NEW`, [0001:208-210](../../../backend/migrations/sql/0001_core_schema.sql)) — 409 возможен только на add/restore.

- [ ] **Step 1: Написать падающие api-тесты (add / exclude / restore / 409 / RBAC)**

В конец `backend/tests/api/test_vendors.py` (файл уже: `from tests import factories as f`, `pytestmark = pytest.mark.db`, импорт `text`):

```python
async def _live_cell_count(db_conn, vendor_id: int) -> int:
    return (
        await db_conn.execute(
            text(
                "SELECT count(*) FROM listing "
                "WHERE vendor_id = :v AND status = 'allowed' AND deleted_at IS NULL"
            ),
            {"v": vendor_id},
        )
    ).scalar_one()


async def test_add_listings_insert_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-ins")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    s2 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    cat = await f.make_category(db_conn, name="add-ins-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-ins-pos")
    v = await f.make_vendor(db_conn, name="add-ins-v")

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1, s2]}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 2
    # маркер открытого релиза создан
    assert (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one() == 1


async def test_add_listings_undelete_branch_no_history(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-und")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="add-und-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-und-pos")
    v = await f.make_vendor(db_conn, name="add-und-v")
    lid = await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")
    await db_conn.execute(
        text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid}
    )

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1]}
    )
    assert resp.status_code == 204
    # та же строка ожила — не наплодили дубль-историю
    total = (
        await db_conn.execute(
            text("SELECT count(*) FROM listing WHERE position_id = :p AND segment_id = :s AND vendor_id = :v"),
            {"p": pos, "s": s1, "v": v},
        )
    ).scalar_one()
    assert total == 1
    assert await _live_cell_count(db_conn, v) == 1


async def test_add_listings_meta_row_conflict_409(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="add-409")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="add-409-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="add-409-pos")
    v = await f.make_vendor(db_conn, name="add-409-v")
    # живая мета-строка (requirement) в ячейке → добавить вендора нельзя
    await f.make_listing(
        db_conn, position_id=pos, segment_id=s1, vendor_id=None, status="requirement", spec_text="Россия"
    )

    resp = await client.post(
        f"/vendors/{v}/listings", json={"position_id": pos, "segment_ids": [s1]}
    )
    assert resp.status_code == 409


async def test_exclude_class_scale(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="exc-cls")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="exc-cls-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="exc-cls-pos")
    v = await f.make_vendor(db_conn, name="exc-cls-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "class", "position_id": pos, "segment_id": s1},
    )
    assert resp.status_code == 200
    assert resp.json() == {"excluded_positions": 1, "excluded_classes": 1}
    assert await _live_cell_count(db_conn, v) == 0


async def test_exclude_position_scale(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="exc-pos")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    s2 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    cat = await f.make_category(db_conn, name="exc-pos-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="exc-pos-pos")
    v = await f.make_vendor(db_conn, name="exc-pos-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos, segment_id=s2, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "position", "position_id": pos, "building_type_id": bt},
    )
    assert resp.status_code == 200
    assert resp.json() == {"excluded_positions": 1, "excluded_classes": 2}


async def test_exclude_standard_scale(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="exc-std")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="exc-std-cat")
    pos1 = await f.make_position(db_conn, category_id=cat, name="exc-std-p1")
    pos2 = await f.make_position(db_conn, category_id=cat, name="exc-std-p2")
    v = await f.make_vendor(db_conn, name="exc-std-v")
    await f.make_listing(db_conn, position_id=pos1, segment_id=s1, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=pos2, segment_id=s1, vendor_id=v, status="allowed")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "standard", "building_type_id": bt},
    )
    assert resp.status_code == 200
    assert resp.json() == {"excluded_positions": 2, "excluded_classes": 2}
    assert await _live_cell_count(db_conn, v) == 0


async def test_exclude_noop_returns_zeros_no_marker(client, as_admin, db_conn) -> None:
    """Нечего исключать (нет живых allowed-строк) → 200, нули, open-маркер НЕ создан.
    Прямая проверка семантики «маркер только при rowcount>0» (решение #2)."""
    bt = await f.make_building_type(db_conn, code="exc-noop")
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    v = await f.make_vendor(db_conn, name="exc-noop-v")

    resp = await client.post(
        f"/vendors/{v}/listings/exclude",
        json={"scope": "standard", "building_type_id": bt},
    )
    assert resp.status_code == 200  # идемпотентно, НЕ 404
    assert resp.json() == {"excluded_positions": 0, "excluded_classes": 0}
    # rowcount==0 → ensure_open_release не вызван → фантомного черновика нет
    assert (
        await db_conn.execute(
            text("SELECT count(*) FROM release WHERE building_type_id = :bt AND status = 'open'"),
            {"bt": bt},
        )
    ).scalar_one() == 0


async def test_restore_undelete_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="res-und")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="res-und-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="res-und-pos")
    v = await f.make_vendor(db_conn, name="res-und-v")
    lid = await f.make_listing(db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed")
    await db_conn.execute(text("UPDATE listing SET deleted_at = now() WHERE id = :id"), {"id": lid})

    resp = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": pos, "segment_id": s1}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 1


async def test_restore_insert_branch(client, as_admin, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="res-ins")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="res-ins-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="res-ins-pos")
    v = await f.make_vendor(db_conn, name="res-ins-v")
    # никакой строки нет (excluded = released−live, живой строки в БД может не быть)

    resp = await client.post(
        f"/vendors/{v}/listings/restore", json={"position_id": pos, "segment_id": s1}
    )
    assert resp.status_code == 204
    assert await _live_cell_count(db_conn, v) == 1


async def test_patch_kind(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="kind-v", kind="manufacturer")
    resp = await client.patch(f"/vendors/{v}", json={"kind": "supplier"})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "supplier"


async def test_patch_kind_invalid_422(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="kind-bad-v")
    resp = await client.patch(f"/vendors/{v}", json={"kind": "producer"})
    assert resp.status_code == 422


async def test_listing_mutations_rbac_viewer_403(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="rbac-v")
    r1 = await client.post(f"/vendors/{v}/listings", json={"position_id": 1, "segment_ids": [1]})
    r2 = await client.post(f"/vendors/{v}/listings/exclude", json={"scope": "standard", "building_type_id": 1})
    r3 = await client.post(f"/vendors/{v}/listings/restore", json={"position_id": 1, "segment_id": 1})
    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403
```

Create/append `backend/tests/api/test_meta.py`:

```python
"""Мета-справочники: /meta/positions для комбобокса «+ стандарт»."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_meta_positions_scoped_to_building_type(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="mp-bt")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="mp-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="Насосы дренажные")
    other = await f.make_position(db_conn, category_id=cat, name="Позиция-без-листинга")
    v = await f.make_vendor(db_conn, name="mp-v")
    await f.make_listing(db_conn, position_id=pos, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get(f"/meta/positions?building_type_id={bt}")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert "Насосы дренажные" in names       # есть живой листинг в этом типе
    assert "Позиция-без-листинга" not in names  # листинга нет → не в выборке
    _ = other  # noqa: F841 — намеренно не в результате


async def test_meta_positions_search(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="mp-q")
    seg = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    cat = await f.make_category(db_conn, name="mp-q-cat")
    p1 = await f.make_position(db_conn, category_id=cat, name="Насосы")
    p2 = await f.make_position(db_conn, category_id=cat, name="Радиаторы")
    v = await f.make_vendor(db_conn, name="mp-q-v")
    await f.make_listing(db_conn, position_id=p1, segment_id=seg, vendor_id=v, status="allowed")
    await f.make_listing(db_conn, position_id=p2, segment_id=seg, vendor_id=v, status="allowed")

    resp = await client.get(f"/meta/positions?building_type_id={bt}&q=насос")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"Насосы"}
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd backend; uv run pytest tests/api/test_vendors.py tests/api/test_meta.py -v`
Expected: FAIL (эндпоинтов/поля `kind` ещё нет: 404/405/422-без-kind).

- [ ] **Step 3: Схемы**

В `backend/app/schemas/__init__.py`:

1) Расширить импорт pydantic (добавить `model_validator`):

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
```

2) `VendorHeaderUpdate` — добавить поле `kind` и валидатор enum (значения — из `vendor_kind`, [0001:20](../../../backend/migrations/sql/0001_core_schema.sql)):

```python
_VENDOR_KINDS = {"manufacturer", "supplier", "other"}


class VendorHeaderUpdate(BaseModel):
    """Инлайн-правка шапки. Partial: в эндпоинте читаем model_dump(exclude_unset=True),
    чтобы отличить «поле не пришло» от «note: null (очистить)»."""

    name: str | None = None
    note: str | None = None
    kind: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Имя не может быть пустым")
        return stripped

    @field_validator("kind")
    @classmethod
    def _kind_in_enum(cls, v: str | None) -> str | None:
        if v is not None and v not in _VENDOR_KINDS:
            raise ValueError("Недопустимый тип вендора")
        return v
```

3) Тела/ответ listing-мутаций (после блока «Мутации карточки вендора»):

```python
class ListingAdd(BaseModel):
    position_id: int
    segment_ids: list[int] = Field(min_length=1)


class ListingExclude(BaseModel):
    """scope-дискриминатор. Обязательность полей — по scope (валидатор)."""

    scope: Literal["class", "position", "standard"]
    position_id: int | None = None
    segment_id: int | None = None
    building_type_id: int | None = None

    @model_validator(mode="after")
    def _require_scope_fields(self) -> "ListingExclude":
        if self.scope == "class" and (self.position_id is None or self.segment_id is None):
            raise ValueError("scope=class требует position_id и segment_id")
        if self.scope == "position" and (self.position_id is None or self.building_type_id is None):
            raise ValueError("scope=position требует position_id и building_type_id")
        if self.scope == "standard" and self.building_type_id is None:
            raise ValueError("scope=standard требует building_type_id")
        return self


class ListingRestore(BaseModel):
    position_id: int
    segment_id: int


class ListingExcludeResult(BaseModel):
    excluded_positions: int
    excluded_classes: int
```

4) `MetaPosition` (в блок «Справочники / мета»):

```python
class MetaPosition(BaseModel):
    id: int
    name: str
    category_path: str | None
```

- [ ] **Step 4: Эндпоинты vendors.py**

В `backend/app/routers/vendors.py`:

1) Импорты — добавить `DBAPIError` и новые схемы:

```python
from sqlalchemy.exc import DBAPIError, IntegrityError
```

```python
from ..schemas import (
    AgreementToggle,
    AliasCreate,
    ListingAdd,
    ListingExclude,
    ListingExcludeResult,
    ListingRestore,
    VendorAlias,
    VendorCard,
    VendorHeaderUpdate,
    VendorRepresents,
    WhereAllowed,
    WhereAllowedChip,
    WhereAllowedPosition,
    WhereAllowedStandard,
)
```

2) Хелпер трансляции триггера (после `_ensure_vendor`):

```python
def _is_cell_chk(exc: DBAPIError) -> bool:
    """listing_cell_chk поднимает RAISE EXCEPTION (SQLSTATE P0001), не нарушение
    ограничения — это НЕ IntegrityError. Распознаём по sqlstate оригинала asyncpg."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == "P0001"


async def _segment_building_type(conn: AsyncConnection, segment_id: int) -> int:
    bt = (
        await conn.execute(
            text("SELECT building_type_id FROM segment WHERE id = :s"), {"s": segment_id}
        )
    ).scalar_one_or_none()
    if bt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Класс не найден")
    return bt


async def _add_one_class(
    conn: AsyncConnection, vendor_id: int, position_id: int, segment_id: int
) -> bool:
    """Один класс: если уже жив — no-op (idempotent), возвращает False; иначе
    un-delete последней soft-deleted строки (чистим и deleted_by, чтобы ожившая
    строка не унесла устаревшего удалившего), иначе INSERT allowed — возвращает True
    (реальное изменение → вызывающий создаст open-маркер). Мета-строка в ячейке → 409."""
    live = (
        await conn.execute(
            text(
                "SELECT 1 FROM listing WHERE position_id = :p AND segment_id = :s "
                "AND vendor_id = :v AND deleted_at IS NULL"
            ),
            {"p": position_id, "s": segment_id, "v": vendor_id},
        )
    ).scalar_one_or_none()
    if live is not None:
        return False  # уже живой — no-op, маркер релиза не нужен
    try:
        res = await conn.execute(
            text(
                "UPDATE listing SET deleted_at = NULL, deleted_by = NULL WHERE id = ("
                "  SELECT id FROM listing WHERE position_id = :p AND segment_id = :s "
                "  AND vendor_id = :v AND deleted_at IS NOT NULL ORDER BY id DESC LIMIT 1)"
            ),
            {"p": position_id, "s": segment_id, "v": vendor_id},
        )
        if res.rowcount == 0:
            await conn.execute(
                text(
                    "INSERT INTO listing (position_id, segment_id, vendor_id, status) "
                    "VALUES (:p, :s, :v, 'allowed')"
                ),
                {"p": position_id, "s": segment_id, "v": vendor_id},
            )
        return True  # ожил (un-delete) ЛИБО вставлен — реальное изменение
    except DBAPIError as exc:
        if _is_cell_chk(exc):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Ячейка содержит требование/прочерк — сначала уберите мета-строку"
            ) from exc
        raise
```

3) Три эндпоинта (после `remove_alias`):

```python
@router.post("/{vendor_id}/listings", status_code=status.HTTP_204_NO_CONTENT)
async def add_listings(
    vendor_id: int,
    body: ListingAdd,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    """Добавить вендора в позицию по классам. Общий для «+ класс»/«+ позиция»/«+ стандарт».
    Порядок блокировок listing → release ЕДИНЫЙ во всех мутациях (без дедлока при
    конкурентной правке одного типа): сперва пишем в listing, ensure_open_release —
    ПОСЛЕ и только если хоть один класс реально ожил (no-op не плодит фантомный
    черновик на дашборде, O2)."""
    await _ensure_vendor(conn, vendor_id)
    bt = await _segment_building_type(conn, body.segment_ids[0])
    changed = False
    for seg in body.segment_ids:
        if await _add_one_class(conn, vendor_id, body.position_id, seg):
            changed = True
    if changed:
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{vendor_id}/listings/exclude", response_model=ListingExcludeResult)
async def exclude_listings(
    vendor_id: int,
    body: ListingExclude,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> ListingExcludeResult:
    """Soft-delete вендора по scope (class/position/standard); deleted_by/аудит
    проставят триггеры. Порядок listing → release (как в add/restore): soft-delete
    СНАЧАЛА, ensure_open_release — ПОСЛЕ и только если реально исключили строки
    (rowcount>0; no-op не создаёт фантомный черновик, O2). Возвращает ФАКТИЧЕСКИЙ
    масштаб (для тоста/сверки; клиентский предрасчёт — только для мгновенного диалога)."""
    await _ensure_vendor(conn, vendor_id)
    if body.scope == "class":
        assert body.segment_id is not None  # гарантировано валидатором
        bt = await _segment_building_type(conn, body.segment_id)
    else:
        bt = body.building_type_id
        assert bt is not None

    if body.scope == "class":
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND position_id = :p AND segment_id = :s "
            "AND deleted_at IS NULL RETURNING position_id"
        )
        params: dict[str, object] = {"v": vendor_id, "p": body.position_id, "s": body.segment_id}
    elif body.scope == "position":
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND position_id = :p AND deleted_at IS NULL "
            "AND segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
            "RETURNING position_id"
        )
        params = {"v": vendor_id, "p": body.position_id, "bt": bt}
    else:  # standard
        sql = (
            "UPDATE listing SET deleted_at = now() "
            "WHERE vendor_id = :v AND deleted_at IS NULL "
            "AND segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt) "
            "RETURNING position_id"
        )
        params = {"v": vendor_id, "bt": bt}

    pos_ids = (await conn.execute(text(sql), params)).scalars().all()
    if pos_ids:  # rowcount>0 → реальное изменение → создаём/переиспользуем open-маркер
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return ListingExcludeResult(
        excluded_classes=len(pos_ids),
        excluded_positions=len(set(pos_ids)),
    )


@router.post("/{vendor_id}/listings/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_listing(
    vendor_id: int,
    body: ListingRestore,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> Response:
    """«Вернуть» один класс: un-delete-first-else-INSERT (O1). Порядок listing →
    release (как в add/exclude): сперва оживляем класс, ensure_open_release — ПОСЛЕ и
    только если реально изменили (уже-живой класс = no-op). Конфликт с мета-строкой → 409."""
    await _ensure_vendor(conn, vendor_id)
    bt = await _segment_building_type(conn, body.segment_id)
    if await _add_one_class(conn, vendor_id, body.position_id, body.segment_id):
        await conn.execute(text("SELECT ensure_open_release(:bt)"), {"bt": bt})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

> `_add_one_class` переиспользуется add и restore (одна семантика «оживить класс»). Порядок регистрации роутов не важен (FastAPI матчит по полному пути; `/{vendor_id}/listings` и `/{vendor_id}/listings/exclude` не конфликтуют).

4) Ветка `kind` в `update_vendor_header` — добавить перед `return await _load_vendor_card(...)`:

```python
    if "kind" in data:
        await conn.execute(
            text("UPDATE vendor SET kind = :k WHERE id = :id"),
            {"k": data["kind"], "id": vendor_id},
        )
```

> Значение уже провалидировано (`_kind_in_enum`). Bind в enum-колонку работает так же, как в `factories.make_vendor` (тип берётся из целевой колонки).

- [ ] **Step 5: Эндпоинт `/meta/positions`**

В `backend/app/routers/meta.py`:

1) Импорт схемы: `from ..schemas import BuildingType, MetaPosition, Segment`.

2) Эндпоинт (после `segments`):

```python
@router.get("/positions", response_model=list[MetaPosition])
async def positions(
    building_type_id: int,
    q: str | None = None,
    conn: AsyncConnection = Depends(read_conn),
) -> list[MetaPosition]:
    """Позиции, реально присутствующие в живом перечне типа объекта (для комбобокса
    «+ стандарт»). Тип достижим только через segment.building_type_id. q — поиск по
    имени/пути раздела. Лимит 50 (комбобокс с сужением по вводу)."""
    params: dict[str, Any] = {"bt": building_type_id}
    q_f = ""
    if q:
        q_f = "AND (p.name ILIKE :q OR category_path(p.category_id) ILIKE :q)"
        params["q"] = f"%{q}%"
    rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT p.id, p.name, category_path(p.category_id) AS category_path "
                "FROM position p "
                "JOIN listing l ON l.position_id = p.id AND l.deleted_at IS NULL "
                "JOIN segment s ON s.id = l.segment_id "
                f"WHERE s.building_type_id = :bt {q_f} "
                "ORDER BY p.name LIMIT 50"
            ),
            params,
        )
    ).mappings()
    return [MetaPosition.model_validate(dict(r)) for r in rows]
```

- [ ] **Step 6: Прогнать — PASS + типы**

Run: `cd backend; uv run pytest tests/api/test_vendors.py tests/api/test_meta.py -v` — Expected: PASS (все новые + старые).
Run: `cd backend; uv run mypy app` — Expected: без ошибок.
Run: `just types` — Expected: `schema.d.ts` содержит `ListingExclude`/`ListingExcludeResult`/`MetaPosition` и пути `/vendors/{vendor_id}/listings(/exclude|/restore)`, `/meta/positions`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/app/routers/meta.py backend/tests/api/test_vendors.py backend/tests/api/test_meta.py
git commit -m "feat(api): listing-мутации add/exclude/restore + PATCH kind + /meta/positions"
```

> `schema.d.ts` gitignored — не стейджим.

---

## Task 3: Типографика v3 + переписать устаревшие тексты

**Files:**
- Modify: `frontend/src/screens/vendors/model.ts`
- Modify: `frontend/src/screens/vendors/model.test.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Produces: `splitQualifier(name) -> {head, qualifier}`, `excludeScaleForPosition(pos) -> {positions,classes}`, `excludeScaleForStandard(std) -> {positions,classes}`, `pluralClasses(n) -> string`; переписанные `excludedTooltip`/`whereAllowedLegend` (язык релиза). Используются в Task 5/6.

> **Долг текстов (проверено в коде).** `excludedTooltip` ([model.ts:48-52](../../../frontend/src/screens/vendors/model.ts)) сейчас говорит «исключён в текущем черновике»; `whereAllowedLegend()` — **без аргумента** ([model.ts:103-105](../../../frontend/src/screens/vendors/model.ts)) — возвращает «показано текущее состояние стандартов». Это старая формулировка, противоречит исправленной модели. Переписываем на язык «войдёт в следующий релиз».

- [ ] **Step 1: Падающие юниты хелперов**

В `frontend/src/screens/vendors/model.test.ts` добавить импорты `splitQualifier, excludeScaleForPosition, excludeScaleForStandard, pluralClasses` и блок:

```ts
describe("splitQualifier", () => {
  it("без скобки → qualifier null", () => {
    expect(splitQualifier("Радиаторы")).toEqual({ head: "Радиаторы", qualifier: null })
  })
  it("со скобкой → голова и уточнение", () => {
    expect(splitQualifier("Насосы (EC двигатель)")).toEqual({
      head: "Насосы",
      qualifier: "EC двигатель",
    })
  })
  it("несбалансированная скобка → всё после '(' как уточнение", () => {
    expect(splitQualifier("Клапаны (Ду50")).toEqual({ head: "Клапаны", qualifier: "Ду50" })
  })
})

describe("excludeScale*", () => {
  const pos = (states: string[]) => ({ chips: states.map((state) => ({ state })) })
  it("позиция: масштаб = число allowed", () => {
    expect(excludeScaleForPosition(pos(["allowed", "allowed", "excluded"]))).toEqual({
      positions: 1,
      classes: 2,
    })
  })
  it("позиция без allowed → ноль позиций", () => {
    expect(excludeScaleForPosition(pos(["excluded"]))).toEqual({ positions: 0, classes: 0 })
  })
  it("стандарт: суммирует allowed по позициям, позиции с allowed", () => {
    const std = { positions: [pos(["allowed", "allowed"]), pos(["allowed"]), pos(["excluded"])] }
    expect(excludeScaleForStandard(std)).toEqual({ positions: 2, classes: 3 })
  })
})

describe("pluralClasses", () => {
  it("склонение", () => {
    expect(pluralClasses(1)).toBe("класс")
    expect(pluralClasses(2)).toBe("класса")
    expect(pluralClasses(5)).toBe("классов")
  })
})
```

Run: `cd frontend; npm run test -- model.test` — Expected: FAIL (хелперов нет).

- [ ] **Step 2: Реализовать хелперы + переписать тексты**

В `frontend/src/screens/vendors/model.ts`:

1) Переписать `excludedTooltip` и `whereAllowedLegend` (язык релиза):

```ts
/** Тултип зачёркнутого чипа: релиз идентифицируется label. Язык — «войдёт в следующий релиз». */
export function excludedTooltip(releaseLabel: string | null): string {
  return releaseLabel
    ? `Был в релизе «${releaseLabel}», исключён — войдёт в следующий релиз`
    : "Был в последнем релизе, исключён — войдёт в следующий релиз"
}
```

```ts
/**
 * Базовая легенда под деревом «Где разрешён». Вариант с образцом-чипом (при
 * наличии excluded) рендерится инлайн в компоненте — здесь базовый текст.
 */
export function whereAllowedLegend(): string {
  return "исключения войдут в следующий релиз; текущие релизы не затрагиваются"
}
```

2) Добавить `splitQualifier`, счётчики масштаба и `pluralClasses`:

```ts
/**
 * Делит имя позиции на «голову» и уточнение в скобках для презентации (первая
 * открывающая скобка). «Насосы (EC двигатель)» → {head:"Насосы", qualifier:"EC двигатель"}.
 * Нет скобки → qualifier=null. Презентационно, НЕ парсер данных.
 */
export function splitQualifier(name: string): { head: string; qualifier: string | null } {
  const i = name.indexOf("(")
  if (i === -1) return { head: name.trim(), qualifier: null }
  const head = name.slice(0, i).trim()
  const rest = name.slice(i + 1)
  const close = rest.lastIndexOf(")")
  const qualifier = (close === -1 ? rest : rest.slice(0, close)).trim()
  return { head: head || name.trim(), qualifier: qualifier || null }
}

/** Масштаб исключения по позиции для диалога (клиентский предрасчёт из дерева). */
export function excludeScaleForPosition(position: PositionLike): {
  positions: number
  classes: number
} {
  const classes = position.chips.filter((c) => c.state === "allowed").length
  return { positions: classes > 0 ? 1 : 0, classes }
}

/** Масштаб исключения по стандарту для диалога (клиентский предрасчёт из дерева). */
export function excludeScaleForStandard(standard: { positions: PositionLike[] }): {
  positions: number
  classes: number
} {
  let positions = 0
  let classes = 0
  for (const p of standard.positions) {
    const c = p.chips.filter((x) => x.state === "allowed").length
    if (c > 0) positions++
    classes += c
  }
  return { positions, classes }
}

/** Русское склонение «класс» по числу. */
export function pluralClasses(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return "класс"
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "класса"
  return "классов"
}
```

- [ ] **Step 3: Типографика v3 в блоке (презентационно)**

В `frontend/src/screens/vendors/VendorCardScreen.tsx` — блок «Где разрешён» довести до v3 **без изменения логики данных** (правило «все классы» уже работает). Правки в разметке:

1) Импорт `splitQualifier`, иконки `CheckCheck` из lucide:

```tsx
import { Award, CheckCheck, ChevronRight, Merge, Plus, Star, X } from "lucide-react"
```

```tsx
import {
  avatarInitial,
  excludedTooltip,
  hasExcludedChips,
  isAllClasses,
  kindLabel,
  pluralPositions,
  pluralStandards,
  pluralVendors,
  splitQualifier,
  standardAllClasses,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"
```

2) **Полоса стандарта** — имя `text-small font-medium tracking-tight` (единственный medium в блоке); свёрнутый — приглушение имени `text-muted-foreground`, открытый — `text-foreground` (через `group-data-[state=open]`). Счётчик справа — `text-caption text-muted-foreground uppercase`. Триггер (заменить `<span className="flex-1 text-small font-medium">`):

```tsx
                        <span className="flex-1 text-small font-medium tracking-tight text-muted-foreground group-data-[state=open]:text-foreground">
                          {s.building_type_name}
                        </span>
                        <span className="text-caption uppercase text-muted-foreground">
                          {summary}
                        </span>
```

3) **Сводка «все классы»** — тихая строка с mint-иконкой `CheckCheck` (`text-success`), НЕ контурный чип. Заменить ветку `isAllClasses(...) ? <Badge...>все классы</Badge>`:

```tsx
                            {isAllClasses(p, s.segment_count) ? (
                              <span className="flex items-center gap-1 text-caption text-muted-foreground">
                                <CheckCheck className="size-3.5 text-success" aria-hidden />
                                все классы
                              </span>
                            ) : (
```

4) **Позиция** — имя `text-foreground`, уточнение в скобках приглушено (`splitQualifier`) в той же строке; 8px воздуха до чипов уже даёт `gap-y-1.5`+`w-full`. Заменить `<span className="flex-1 text-small">{p.position_name}</span>`:

```tsx
                            <span className="flex-1 text-small text-foreground">
                              {(() => {
                                const { head, qualifier } = splitQualifier(p.position_name)
                                return (
                                  <>
                                    {head}
                                    {qualifier && (
                                      <span className="text-muted-foreground">
                                        {" "}
                                        ({qualifier})
                                      </span>
                                    )}
                                  </>
                                )
                              })()}
                            </span>
```

5) **Легенда** — обновлённые тексты уже подтянутся из `whereAllowedLegend()`/`excludedTooltip`; инлайн-текст образца-чипа привести к новой формулировке (заменить строку «— был в последнем релизе, исключён · {whereAllowedLegend()}»):

```tsx
                — исключён, войдёт в следующий релиз · {whereAllowedLegend()}
```

- [ ] **Step 4: Обновить существующие тесты под новые тексты + смоук v3**

В `frontend/src/screens/vendors/VendorCardScreen.test.tsx`:

1) Тест «раскрывает стандарт … зачёркнутый excluded с тултипом» — обновить ожидаемый `aria-label` (было «исключён в текущем черновике»):

```tsx
    expect(excluded).toHaveAttribute(
      "aria-label",
      "Был в релизе «ред. 25.03.2026», исключён — войдёт в следующий релиз"
    )
```

2) Тест «данные без исключённых: легенда без пояснения…» — обновить ожидаемый текст легенды:

```tsx
    expect(
      await screen.findByText(/исключения войдут в следующий релиз/)
    ).toBeInTheDocument()
```

3) Тест «легенда без рамки: при excluded — образец-чип и пояснение» — regex остаётся валидным (`/исключён, войдёт в следующий релиз/`):

```tsx
    expect(
      await screen.findByText(/исключён, войдёт в следующий релиз/)
    ).toBeInTheDocument()
```

4) Добавить смоук v3 (split уточнения + сводка с иконкой). В `describe("VendorCardScreen — Где разрешён")`:

```tsx
it("уточнение позиции в скобках приглушено (split)", async () => {
  server.use(
    http.get("/api/vendors/:vendorId/where-allowed", () =>
      HttpResponse.json({
        standards: [
          {
            building_type_id: 1,
            building_type_name: "Жилой дом",
            position_count: 1,
            segment_count: 2,
            positions: [
              {
                position_id: 100,
                position_name: "Насосы (EC двигатель)",
                chips: [
                  { segment_id: 11, segment_name: "Делюкс", state: "allowed", release_label: null },
                ],
              },
            ],
          },
        ],
      })
    )
  )
  renderAt()
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  await userEvent.click(screen.getByRole("button", { name: /Жилой дом/ }))
  expect(await screen.findByText("(EC двигатель)")).toBeInTheDocument()
})
```

- [ ] **Step 5: Прогнать — PASS + typecheck + format**

Run: `cd frontend; npm run test -- model.test VendorCardScreen` — Expected: PASS.
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.
Run: `cd frontend; npm run format` затем `npm run format:check` — Expected: чисто.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/vendors/model.ts frontend/src/screens/vendors/model.test.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): типографика v3 «Где разрешён» + тексты на язык релиза"
```

---

## Task 4: Каркас edit-режима (view ↔ edit, read-only view, гейтинг InlineEditText)

**Files:**
- Modify: `frontend/src/screens/vendors/InlineEditText.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: `useToggleAgreement`/`useAddAlias`/`useRemoveAlias`/`useUpdateVendorHeader` (без изменений сигнатур).
- Produces: локальный `editMode` state; проп `readOnly` у `InlineEditText`. Точка расширения для Task 5/6 (операции разрешений оживают только в edit).

> **View — дефолт и полностью read-only.** Это ломает существующие тесты мутаций/инлайн-правки (они кликают affordance, которых в view нет). Обновляем их: перед взаимодействием входим в edit.

- [ ] **Step 1: Проп `readOnly` у InlineEditText**

В `frontend/src/screens/vendors/InlineEditText.tsx` — добавить в интерфейс `readOnly?: boolean`, в деструктуризацию, и раннюю ветку до `if (!editing)`:

```tsx
interface InlineEditTextProps {
  value: string
  onSubmit: (next: string) => Promise<void> | void
  ariaLabel: string
  multiline?: boolean
  placeholder?: string
  error?: string | null
  onEditStart?: () => void
  displayClassName?: string
  inputClassName?: string
  readOnly?: boolean
}
```

```tsx
  // ...деструктуризация: добавить readOnly = false
  if (readOnly) {
    const empty = value.trim() === ""
    if (empty) return null // в view пустое примечание не занимает место
    return <span className={displayClassName}>{value}</span>
  }
  if (!editing) {
    // ...без изменений
```

- [ ] **Step 2: Падающие тесты view/edit-каркаса**

В `frontend/src/screens/vendors/VendorCardScreen.test.tsx` добавить helper и `describe`:

```tsx
async function enterEditMode() {
  await userEvent.click(screen.getByRole("button", { name: "Редактировать" }))
}

describe("VendorCardScreen — режим правки", () => {
  it("view по умолчанию: ноль affordance", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(screen.getByRole("button", { name: "Редактировать" })).toBeInTheDocument()
    // тумблер соглашения выключен/недоступен
    expect(screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })).toBeDisabled()
    // нет инлайн-кнопок правки, нет «×» на алиасах, нет «+ вариант»
    expect(screen.queryByRole("button", { name: "Редактировать имя" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /удалить/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "вариант" })).not.toBeInTheDocument()
  })

  it("вход в edit: появляются affordance и баннер", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    expect(screen.getByRole("button", { name: "Готово" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Редактировать имя" })).toBeInTheDocument()
    expect(screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })).not.toBeDisabled()
    expect(screen.getByText(/войдут в следующий релиз/)).toBeInTheDocument()
  })

  it("вход в edit: все стандарты раскрыты", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    // дефолтная фикстура: 1 стандарт «Жилой дом» → раскрыт (виден чип)
    expect(await screen.findByText("Делюкс")).toBeInTheDocument()
  })
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (кнопки «Редактировать»/«Готово», баннера, гейтинга нет).

- [ ] **Step 3: Каркас в VendorCardScreen.tsx**

1) Импорты: `Check`, `Pencil` из lucide.

2) State (после существующих `useState`):

```tsx
  const [editMode, setEditMode] = useState(false)
  const [expanded, setExpanded] = useState<string[]>([])
```

3) Строка над карточками (перед `{/* Шапка */}`) — тумблер режима:

```tsx
      <div className="flex items-center justify-between">
        <span className="text-caption uppercase text-muted-foreground">Вендор</span>
        <Button
          variant={editMode ? "default" : "outline"}
          size="sm"
          className="gap-1.5"
          onClick={() => {
            if (!editMode) setExpanded(standards.map((s) => String(s.building_type_id)))
            setEditMode((v) => !v)
          }}
        >
          {editMode ? <Check className="size-3.5" aria-hidden /> : <Pencil className="size-3.5" aria-hidden />}
          {editMode ? "Готово" : "Редактировать"}
        </Button>
      </div>
      {editMode && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5 text-caption text-muted-foreground">
          Свойства вендора сохраняются сразу · правки разрешений применяются
          немедленно и войдут в следующий релиз (текущие релизы не затрагиваются)
        </div>
      )}
```

> Баннер — subtle-violet через существующий акцент (`border-primary/30 bg-primary/5`), новых токенов нет.

4) Гейтинг шапки: `InlineEditText` имени/примечания — добавить `readOnly={!editMode}`; тумблер соглашения — `disabled={!editMode || toggleAgreement.isPending}`. Бейдж `kind` в view остаётся бейджем (дропдаун `kind` — Task 5, но каркас уже гейтит по `editMode`).

5) Варианты написания: «×» на алиасах и «+ вариант» — обернуть в `{editMode && (...)}`. В view — только чтение чипов.

6) Бренд/объединение: «Объединить» рендерить только в edit (`{editMode && <Button ...>}`); в view блок остаётся, но без кнопки.

7) Аккордеон «Где разрешён» — сделать контролируемым в edit, uncontrolled в view:

```tsx
            <Accordion
              type="multiple"
              className="mt-2.5"
              {...(editMode ? { value: expanded, onValueChange: setExpanded } : {})}
            >
```

- [ ] **Step 4: Обновить существующие тесты под view-default**

В том же файле — существующие тесты, кликающие affordance, снабдить `await enterEditMode()` после `findByRole heading`:
- `describe("VendorCardScreen — мутации")`: «клик по тумблеру…», «добавление alias…».
- `describe("VendorCardScreen — инлайн-правка шапки")`: все 4 теста (имя Enter, 409, note blur, очистка note).
- `describe("VendorCardScreen — шапка")` тест «скрывает заметку, когда она пустая» — в view пустое примечание не рендерит кнопку; после `enterEditMode()` кнопка «Редактировать примечание» с «+ примечание» появится (assertion остаётся). Добавить `await enterEditMode()` перед проверкой.

Пример правки (тест тумблера):

```tsx
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })
    )
```

- [ ] **Step 5: Прогнать — PASS + typecheck + format**

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: PASS (каркас + обновлённые старые).
Run: `cd frontend; npm run typecheck` — без ошибок. Run: `npm run format; npm run format:check` — чисто.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/vendors/InlineEditText.tsx frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): каркас режима правки (view ↔ edit), read-only view, гейтинг InlineEditText"
```

---

## Task 5: Операции класс/позиция/стандарт (+5 UI-примитивов) + «вернуть» + дропдаун kind

**Files:**
- Create: `frontend/src/components/ui/{dialog,popover,command,checkbox,radio-group}.tsx`
- Modify: `frontend/src/api/queries.ts`
- Create: `frontend/src/screens/vendors/ExcludeDialog.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`
- Modify: `frontend/src/test/msw/handlers.ts`

**Interfaces:**
- Consumes: эндпоинты Task 2; `excludeScaleForPosition`/`excludeScaleForStandard`/`pluralClasses`/`pluralPositions` (Task 3); `useUpdateVendorHeader` (расширить `kind`).
- Produces: `useAddListings(id)`, `useExcludeListings(id)` (возвращает `{excluded_positions,excluded_classes}`), `useRestoreListing(id)` — **все гасят 4 ключа** (`["vendor-where-allowed",id]`, `["vendor",id]`, `["matrix"]`, `["dashboard"]`); `ExcludeDialog` (масштаб позиция/стандарт).

- [ ] **Step 1: Добавить 5 shadcn-примитивов В КОНВЕНЦИИ ПРОЕКТА**

> **Сверить импорт Radix ПЕРЕД генерацией — не доверять выводу CLI слепо.** Проект
> (preset b0) импортирует Radix из УНИФИЦИРОВАННОГО пакета `radix-ui`
> (`import { Dialog as DialogPrimitive } from "radix-ui"`), как в существующих
> `components/ui/dropdown-menu.tsx`/`sidebar.tsx` и в `VendorCardScreen.tsx`. Свежий
> shadcn CLI генерит импорты из РАЗДЕЛЬНЫХ `@radix-ui/react-*` — это разойдётся с
> конвенцией проекта и потянет лишние пакеты. Порядок: **(1)** прочитать
> `components/ui/dropdown-menu.tsx` — зафиксировать точный стиль импорта Radix и токены;
> **(2)** сгенерировать/написать 5 новых В ТОЙ ЖЕ конвенции.

```bash
cd frontend; npx --yes shadcn@latest add dialog popover command checkbox radio-group
```

**После генерации обязательно:** переписать импорты Radix на unified `radix-ui`
(сверив с `ui/dropdown-menu.tsx`), не оставлять `@radix-ui/react-*`; не-компонентные
экспорты (если появятся) вынести в `*-variants.ts` (react-refresh lint, как в проекте);
`npm run lint` должен пройти. Если CLI-конфига нет — написать файлы вручную по стоковым
исходникам shadcn на токенах DS, импорт Radix — unified.

- [ ] **Step 2: Хуки мутаций (падающий тест хуков не требуется — покрываются экраном)**

В `frontend/src/api/queries.ts`:

1) Расширить `useUpdateVendorHeader` тип полей на `kind`:

```ts
    mutationFn: async (fields: { name?: string; note?: string; kind?: string }) => {
```

2) Общий инвалидатор + три хука (в конец файла):

```ts
/** Инвалидация после мутации разрешений: 4 ключа (дерево + карточка + матрица + дашборд). */
function invalidatePermissions(qc: ReturnType<typeof useQueryClient>, id: number) {
  qc.invalidateQueries({ queryKey: ["vendor-where-allowed", id] })
  qc.invalidateQueries({ queryKey: ["vendor", id] })
  qc.invalidateQueries({ queryKey: ["matrix"] })
  qc.invalidateQueries({ queryKey: ["dashboard"] })
}

/** Добавить вендора в позицию по классам (общий «+ класс»/«+ позиция»/«+ стандарт»). */
export function useAddListings(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { position_id: number; segment_ids: number[] }) => {
      const { error } = await api.POST("/vendors/{vendor_id}/listings", {
        params: { path: { vendor_id: id } },
        body,
      })
      if (error) throw error
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}

/** Исключить вендора по scope; возвращает фактический масштаб (для тоста). */
export function useExcludeListings(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      scope: "class" | "position" | "standard"
      position_id?: number
      segment_id?: number
      building_type_id?: number
    }) => {
      const { data, error } = await api.POST("/vendors/{vendor_id}/listings/exclude", {
        params: { path: { vendor_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}

/** «Вернуть» один класс. */
export function useRestoreListing(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { position_id: number; segment_id: number }) => {
      const { error } = await api.POST("/vendors/{vendor_id}/listings/restore", {
        params: { path: { vendor_id: id } },
        body,
      })
      if (error) throw error
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}
```

> `useAddAlias`/`useRemoveAlias` — НЕ трогаем (решение 4: `["matrix"]` не добавляем).

- [ ] **Step 3: MSW-хендлеры новых мутаций**

В `frontend/src/test/msw/handlers.ts`, в массив `handlers`:

```ts
  http.post(`${BASE}/vendors/:vendorId/listings`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${BASE}/vendors/:vendorId/listings/exclude`, () =>
    HttpResponse.json({ excluded_positions: 1, excluded_classes: 2 })
  ),
  http.post(`${BASE}/vendors/:vendorId/listings/restore`, () => new HttpResponse(null, { status: 204 })),
  http.get(`${BASE}/meta/positions`, () =>
    HttpResponse.json([{ id: 100, name: "Радиаторы отопления", category_path: "ОВиК" }])
  ),
```

- [ ] **Step 4: ExcludeDialog + операции в блоке**

Create `frontend/src/screens/vendors/ExcludeDialog.tsx` — диалог подтверждения масштаба (позиция/стандарт):

```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

import { pluralClasses, pluralPositions } from "./model"

interface ExcludeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  scale: { positions: number; classes: number }
  pending: boolean
  onConfirm: () => void
}

/**
 * Подтверждение массового исключения (позиция/стандарт). Масштаб — клиентский
 * предрасчёт из уже загруженного дерева (мгновенно, без сети); фактический масштаб
 * придёт в тосте из ответа мутации. Точечное исключение (класс) диалога НЕ требует.
 */
export function ExcludeDialog({
  open,
  onOpenChange,
  title,
  scale,
  pending,
  onConfirm,
}: ExcludeDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Будет исключён из {scale.positions} {pluralPositions(scale.positions)} и{" "}
            {scale.classes} {pluralClasses(scale.classes)}. Исключение применится сразу и
            войдёт в следующий релиз; текущие релизы не затрагиваются.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            Исключить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

В `VendorCardScreen.tsx` — оживить операции (все под `editMode`):

- **kind-дропдаун** (в шапке, edit): бейдж → shadcn `DropdownMenu` (уже есть) с опциями из `KIND_LABELS`; выбор → `updateHeader.mutate({ kind })`.
- **Класс «×»** (edit, на allowed-чипе): мгновенно `excludeListings.mutate({ scope:"class", position_id, segment_id })`, без диалога.
- **«+ класс»** (edit, конец ряда): `Popover` + `Checkbox` со списком недостающих сегментов позиции → `addListings.mutate({ position_id, segment_ids })`. Недостающие = сегменты типа (из where-allowed знаем присутствующие; полный список — `useSegments(building_type_id)`), которых нет среди allowed-чипов.
- **Позиция «⊖»** (edit, справа от имени): открывает `ExcludeDialog` (scope=position), масштаб = `excludeScaleForPosition(p)`; confirm → `excludeListings.mutate({ scope:"position", position_id, building_type_id })`.
- **Стандарт kebab «⋯»** (edit, в полосе): `DropdownMenu` с destructive-пунктом «Исключить из стандарта» → `ExcludeDialog` (scope=standard), масштаб = `excludeScaleForStandard(s)` → `excludeListings.mutate({ scope:"standard", building_type_id })`.
- **«Вернуть»** (edit, рядом с excluded-чипом): `restoreListing.mutate({ position_id, segment_id })`.
- **Развёртка сводок в edit:** когда `editMode`, ветку `isAllClasses(...)` НЕ применяем — всегда показываем полный список чипов (роллап не редактируется). Условие рендера: `!editMode && isAllClasses(p, s.segment_count) ? <сводка> : <чипы>`.

Тост фактического масштаба — через существующий `sonner` (`toast(...)`): `const res = await excludeListings.mutateAsync(...); if (res.excluded_classes > 0) toast(`Исключён из ${res.excluded_positions} …`)`. **Гард на нули** — при no-op (rowcount==0, напр. гонка) тост не показываем (маркер тоже не создан на бэке). (Toaster уже в AppShell.)

- [ ] **Step 5: Тесты операций**

В `VendorCardScreen.test.tsx`, `describe("VendorCardScreen — операции разрешений")`:

```tsx
it("класс «×» → мутация без диалога + появляется «вернуть»", async () => {
  let excludeBody: unknown = null
  server.use(
    http.post("/api/vendors/:vendorId/listings/exclude", async ({ request }) => {
      excludeBody = await request.json()
      return HttpResponse.json({ excluded_positions: 1, excluded_classes: 1 })
    })
  )
  renderAt()
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  await enterEditMode()
  await userEvent.click(screen.getByRole("button", { name: /исключить класс Делюкс/ }))
  await waitFor(() =>
    expect(excludeBody).toMatchObject({ scope: "class", segment_id: 11 })
  )
})

it("«⊖» позиции → диалог с масштабом", async () => {
  renderAt()
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  await enterEditMode()
  await userEvent.click(screen.getByRole("button", { name: /исключить из позиции/ }))
  expect(await screen.findByText(/Будет исключён из/)).toBeInTheDocument()
})

it("kebab стандарта → «Исключить из стандарта» → диалог", async () => {
  renderAt()
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  await enterEditMode()
  await userEvent.click(screen.getByRole("button", { name: /действия стандарта/ }))
  await userEvent.click(await screen.findByText("Исключить из стандарта"))
  expect(await screen.findByText(/Будет исключён из/)).toBeInTheDocument()
})
```

> Точные `aria-label` («исключить класс Делюкс», «исключить из позиции», «действия стандарта») — задать в JSX Step 4; тесты и разметка согласованы.

- [ ] **Step 6: Прогнать — PASS + typecheck + lint + format**

Run: `cd frontend; npm run test -- VendorCardScreen model.test` — PASS.
Run: `cd frontend; npm run typecheck` — без ошибок. Run: `npm run lint` — чисто (react-refresh на новых ui-примитивах). Run: `npm run format; npm run format:check` — чисто.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ui frontend/src/api/queries.ts frontend/src/screens/vendors/ExcludeDialog.tsx frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx frontend/src/test/msw/handlers.ts
git commit -m "feat(vendors): операции класс/позиция/стандарт (исключить/вернуть) + дропдаун kind + 5 ui-примитивов"
```

---

## Task 6: Диалог «+ стандарт» (три шага, dimmed-присутствующие)

**Files:**
- Create: `frontend/src/screens/vendors/AddStandardDialog.tsx`
- Modify: `frontend/src/api/queries.ts` (добавить `useMetaPositions`)
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: `useBuildingTypes` ([queries.ts:90](../../../frontend/src/api/queries.ts)), `useSegments` ([queries.ts:102](../../../frontend/src/api/queries.ts)), новый `useMetaPositions`, `useAddListings` (Task 5); присутствие вендора — из уже загруженного `where-allowed`.
- Produces: `AddStandardDialog` (radio-список стандартов → combobox позиции → чекбоксы классов → `useAddListings`).

- [ ] **Step 1: Хук `useMetaPositions`**

В `frontend/src/api/queries.ts`:

```ts
/** Позиции типа объекта для комбобокса «+ стандарт» (поиск по q). */
export function useMetaPositions(buildingTypeId?: number, q?: string) {
  return useQuery({
    queryKey: ["meta-positions", buildingTypeId, q],
    enabled: buildingTypeId !== undefined,
    queryFn: async () => {
      const { data, error } = await api.GET("/meta/positions", {
        params: { query: { building_type_id: buildingTypeId, q } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/positions")
      return data
    },
  })
}
```

- [ ] **Step 2: Падающий тест диалога**

В `VendorCardScreen.test.tsx`:

```tsx
describe("VendorCardScreen — + стандарт", () => {
  it("открывает диалог; присутствующий стандарт приглушён", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(screen.getByRole("button", { name: "+ стандарт" }))
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    // «Жилой дом» присутствует (id=1 в where-allowed) → помечен «уже присутствует»
    expect(await screen.findByText(/уже присутствует/)).toBeInTheDocument()
  })
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (кнопки «+ стандарт» и диалога нет).

- [ ] **Step 3: AddStandardDialog**

Create `frontend/src/screens/vendors/AddStandardDialog.tsx` — три шага в одном `Dialog`:

1) **Стандарт** — `RadioGroup` по `useBuildingTypes()`; присутствующие (`present: Set<number>` из `where-allowed` `standards.map(s => s.building_type_id)`) — `disabled` + текст «уже присутствует».
2) **Позиция** — `Command` (combobox) по `useMetaPositions(buildingTypeId, q)` с локальным `q`.
3) **Классы** — `Checkbox` по `useSegments(buildingTypeId)`; одноклассовый тип → один чекбокс + пометка «у этого типа один класс».

Подзаголовок диалога: «появится в выбранной позиции; запись применится сразу и войдёт в следующий релиз». «Добавить» → `onAdd({ position_id, segment_ids })` (родитель зовёт `useAddListings`). Пропсы: `open`, `onOpenChange`, `present: Set<number>`, `onAdd`, `pending`.

> Если вендор присутствует во ВСЕХ стандартах — кнопку «+ стандарт» в экране рендерить `disabled` с тултипом «вендор есть во всех стандартах» (проверка `present.size >= buildingTypes.length`).

- [ ] **Step 4: Кнопка «+ стандарт» в блоке**

В `VendorCardScreen.tsx` — внизу блока «Где разрешён» (edit): пунктирная кнопка «+ стандарт» (`border-dashed border-border-strong text-primary`), открывает `AddStandardDialog`. `onAdd` → `addListings.mutate(...)` → закрыть диалог.

- [ ] **Step 5: Прогнать — PASS + typecheck + lint + format**

Run: `cd frontend; npm run test -- VendorCardScreen` — PASS.
Run: `cd frontend; npm run typecheck; npm run lint; npm run format; npm run format:check` — чисто.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/screens/vendors/AddStandardDialog.tsx frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): диалог «+ стандарт» (стандарт → позиция → классы)"
```

---

## Task 7: Финализация — `just ci`, документация, PR

**Files:**
- Modify: `CLAUDE.md`, `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-13-vendor-card-edit-mode.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли` (types → lint → typecheck → test). db-тесты скипаются без `DATABASE_URL_TEST` — ок (прогонятся в CI на ветке Neon). Красно — STOP, чинить, доки поверх красного не писать.

- [ ] **Step 2: Sanity миграции на боевой**

Run: `just migrate-current`
Expected: head = `0006_ensure_open_release` (подтверждает, что боевая база получила ревизию — иначе живой app 500-ит на первой правке разрешений).

- [ ] **Step 3: TECH_DEBT — отложенные follow-up**

В `docs/TECH_DEBT.md` в раздел карточки вендора добавить:

```markdown
- **Поток объединения вендоров.** Кнопка «Объединить» в edit-режиме — заглушка
  «в разработке». Мутации разрешений спроектированы общими (нейтральны к экрану),
  но перенос listing по `represents_id` + слияние — отдельный срез.
- **Редактируемая сетка матрицы.** Listing-мутации (`add`/`exclude`/`restore`)
  vendor-scoped, но операция нейтральна — та же ячейка однажды правится из матрицы.
  Экран матрицы в этом срезе не трогали.
- **Редактирование `release.label` при публикации.** `ensure_open_release` ставит
  нейтральный «<тип> — рабочая версия»; `freeze_release` его не перезаписывает.
  Уточнение label человеком — на будущем экране изданий (§5).
```

- [ ] **Step 4: CLAUDE.md (карта / §5 / §6)**

- Карта репо, `routers/vendors.py`: отметить listing-мутации `POST /vendors/{id}/listings(/exclude|/restore)` (add/exclude/restore, порядок listing→release, `ensure_open_release` после записи при rowcount>0, `listing_cell_chk`→409 через SQLSTATE P0001), `PATCH kind`; `meta.py` — `GET /meta/positions`; `migrations/versions` — `0006_ensure_open_release`.
- Карта репо, `screens/vendors/`: `editMode`/`expanded`, `InlineEditText.readOnly`, `ExcludeDialog`/`AddStandardDialog`, хелперы `splitQualifier`/`excludeScaleFor*`/`pluralClasses`, новые ui-примитивы `dialog`/`popover`/`command`/`checkbox`/`radio-group`.
- §5 (карточка вендора): отметить режим правки + мутации разрешений + типографику v3.
- §6-тест «где живёт логика»: единственность open-маркера/soft-delete/«ячейка = вендоры ЛИБО мета» — в БД (инвариант); режим/диалоги/масштаб-предрасчёт — на фронте (процесс/экран).

- [ ] **Step 5: Devlog**

Create `docs/devlog/2026-07-13-vendor-card-edit-mode.md` — хронология: ключевая находка (черновик — не песочница: `listing` без `release_id`, правки в живое, «Готово» ничего не коммитит); ревизия 0006 `ensure_open_release` (гонка на `uq_release_one_open`, нейтральный label т.к. `freeze_release` не трогает label); единый scoped-exclude (обоснование vs три ручки; building_type только через `segment`); маркер open-релиза ПОСЛЕ записи и только при реальном изменении (rowcount>0, не на no-op), порядок блокировок listing→release един во всех трёх (без дедлока); трансляция `listing_cell_chk`→409 через SQLSTATE P0001 (не IntegrityError!); двухфазный масштаб (клиент-предрасчёт + сервер-факт, без preview-эндпоинта); инвалидация 4 ключей у мутаций разрешений (алиасы — без `["matrix"]`); view-default сломал старые тесты → обновлены; типографика v3. Отметить 5 решённых заказчиком вопросов.

- [ ] **Step 6: Commit + push + PR**

```bash
git add CLAUDE.md docs/TECH_DEBT.md docs/devlog/2026-07-13-vendor-card-edit-mode.md
git commit -m "docs(vendor-card-edit-mode): devlog + CLAUDE.md карта/§5/§6 + TECH_DEBT"
git push -u origin feat/vendor-card-edit-mode
gh pr create --base main --title "feat: режим правки карточки вендора + типографика v3 «Где разрешён»" --body "..."
```

---

## Self-Review

**Spec coverage:**
- §A (живой listing + маркер open-релиза, «Готово» не коммитит) → Task 1 (функция) + Task 4 (каркас) + Task 7 (devlog). ✓
- §B контракт мутаций (add/exclude/restore, `PATCH kind`, `ensure_open_release` после записи при rowcount>0 — порядок listing→release, 409-трансляция, divergence #1 `kind`) → Task 2. Решение 2 (единый scoped-exclude) закреплено. ✓
- §C ревизия 0006 (чистый SQL, гонка на ограничении, label-текст) → Task 1. Решение 5 (нейтральный label, freeze_release не трогаем) закреплено. ✓
- §D инвалидация (4 ключа у мутаций разрешений; алиасы без `["matrix"]`) → Task 5. Решение 4 закреплено. ✓
- §E типографика v3 (уровни, `splitQualifier`, сводка `CheckCheck`, тексты) → Task 3. ✓
- §F каркас режима (тумблер, баннер, read-only view, гейтинг InlineEditText) → Task 4. ✓
- §G операции 3 уровней (× класс без диалога, ⊖/kebab с диалогом масштаба, «вернуть») → Task 5. Решение 3 (двухфазный масштаб) закреплено. ✓
- §H диалог «+ стандарт» (три шага, dimmed-присутствующие, `/meta/positions` net-new) → Task 6 (+ эндпоинт в Task 2). ✓
- Новые UI-примитивы (5) → Task 5. ✓
- Тесты (backend: add/exclude/restore 3 уровня, `ensure_open_release` create+idempotent, cell_chk→409, RBAC 403; frontend: view/edit, split, сводка, диалоги масштаба, «+ стандарт») → Task 1/2/3/4/5/6. ✓
- Границы (merge/матрица/список/C1/C2/SSO не здесь; freeze_release не трогаем) → Task 7 TECH_DEBT + Global Constraints. ✓

**Контрактные находки против кода (код > спека, зафиксировано):**
1. `segment_count` и хелперы `isAllClasses`/`standardAllClasses`/`hasExcludedChips` **уже в коде** (PR #22) — Task 3 их не пересоздаёт, только использует.
2. `whereAllowedLegend()` — **без аргумента** (спека-черновик писала `(false)`); Task 3 сохраняет сигнатуру без аргумента.
3. `listing_cell_chk` = `RAISE EXCEPTION` (SQLSTATE **P0001**), **не** `IntegrityError` → Task 2 ловит `DBAPIError` + `_is_cell_chk`.
4. `freeze_release` (0001:396-400) **не трогает label** → обоснование нейтрального label (решение 5) верно.
5. building_type достижим **только** через `segment.building_type_id` → scoped-WHERE в Task 2 построены на этом.
6. View-default **ломает существующие тесты** мутаций/инлайн-правки → Task 4 их обновляет (не пропущено).

**Placeholder scan:** код полный в каждом шаге. «...» — только в `gh pr create --body` (Task 7). Для UI Task 5/6 несколько шагов описывают JSX структурно с точными токенами/`aria-label` (согласованы с тестами) — не placeholder, а точная инструкция при полном коде хуков/диалогов/хелперов.

**Type consistency:** `ListingExclude`/`ListingExcludeResult`/`ListingAdd`/`ListingRestore`/`MetaPosition` (Task 2 схемы) ↔ хуки `useExcludeListings`/`useAddListings`/`useRestoreListing`/`useMetaPositions` (Task 5/6) ↔ тела MSW (Task 5). `excludeScaleFor*`/`pluralClasses` (Task 3) ↔ `ExcludeDialog` (Task 5). `ensure_open_release(int)→int` (Task 1) ↔ вызовы `SELECT ensure_open_release(:bt)` (Task 2). `InlineEditText.readOnly` (Task 4) ↔ `readOnly={!editMode}` (Task 4). `_is_cell_chk` (Task 2) — единое имя.

---

## Execution Handoff

(Заполняется контроллером при запуске.) Рекомендация по моделям (память проекта): Task 1/2 — Sonnet (SQL/бэкенд, клиент будет ревьюить scoped-WHERE и 409-трансляцию — ревью на Opus); Task 3 — Haiku→Sonnet (чистые хелперы + вёрстка); Task 4/5/6 — Sonnet (интеграция, Radix-диалоги/поповеры); Task 7 — Haiku (доки). Оркестрация + ревью — Opus. Одна ветка `feat/vendor-card-edit-mode`, коммит на задачу, единый PR в Task 7.
