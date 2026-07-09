# Декомпозиция записи сид-импорта — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать `app/seed/loader.execute` с ~14k построчных INSERT на пакетные `executemany` в той же одной транзакции (минуты → секунды), сохранив атомарность §14 и все инварианты db-тестов; добавить операционную страховку таймаутами.

**Architecture:** id для `category`/`position`/`vendor` предвыделяются батчем через `nextval(pg_get_serial_sequence(...))` (документированно, без RETURNING), карты строятся в Python, затем 4 единообразных `executemany` с явными id. `run()` перед `execute` ставит `SET LOCAL statement_timeout`/`idle_in_transaction_session_timeout`. Всё в одной транзакции — ROLLBACK при любом сбое.

**Tech Stack:** Python 3.12, SQLAlchemy Core (async, asyncpg), PostgreSQL 18 (Neon), pytest + pytest-asyncio (маркер `db`).

## Global Constraints

- **БД — источник истины (schema-first).** ORM как владелец схемы запрещён; только SQLAlchemy Core. Ничего вычислимого (светофор/`compliance_pct`/звезда) в коде не пересчитываем.
- **Не коммитить в `main`.** Работа на ветке `feat/seed-writepath-decomposition` (уже создана), PR в `main`.
- **Перед пушем — локальный `just ci`** (types, lint/ruff, mypy `app`, pytest+db, vitest), не ручной набор.
- **Инвертированный TDD для db-тестов:** логика БД (триггеры/вьюхи/FK) уже есть — ждём PASS. FAIL = ошибка теста/понимания схемы, БД не правим.
- **db-тесты** идут против тест-ветки Neon; без `DATABASE_URL_TEST` скипаются. Единичный прогон: `cd backend; uv run pytest <node-id> -v`. Полный db-набор: `cd backend; uv run pytest -m db -v`.
- **`set_config('app.user', …, true)` остаётся ПЕРВЫМ statement'ом внутри `execute()`** (до любых DML) — аудит-триггеры берут автора отсюда. Логин — bind-параметром, не конкатенацией.
- Источник истины по решениям — [спека](../specs/2026-07-09-seed-writepath-decomposition-design.md).

---

### Task 1: Хелпер `_apply_timeouts` + обвязка `run()`

Операционная страховка сессии сида. Изолирована от `execute` — тестируется первой.

**Files:**
- Modify: `backend/app/seed/loader.py` (добавить `_apply_timeouts`; вызвать в `run()` внутри `begin()`, до `execute`)
- Test: `backend/tests/db/test_seed_loader.py` (новый тест применения GUC)

**Interfaces:**
- Produces: `async def _apply_timeouts(conn: AsyncConnection) -> None` — выполняет два `SET LOCAL` (`statement_timeout='60s'`, `idle_in_transaction_session_timeout='15s'`).

- [ ] **Step 1: Написать тест применения таймаутов**

В конец `backend/tests/db/test_seed_loader.py` добавить (импорт `_apply_timeouts` — локально в тесте, чтобы не тянуть приватное имя в шапку):

```python
async def test_apply_timeouts_sets_session_guc(db_conn) -> None:
    # Тестируем ПРИМЕНЕНИЕ настроек (не эффект — эффект без медленного оператора
    # не воспроизвести). Ловит класс ошибок единиц измерения: SET ... = 60 это 60 мс.
    from app.seed.loader import _apply_timeouts

    await _apply_timeouts(db_conn)
    st = (await db_conn.execute(text("SHOW statement_timeout"))).scalar_one()
    idl = (await db_conn.execute(
        text("SHOW idle_in_transaction_session_timeout"))).scalar_one()
    # PG нормализует GUC-длительность к крупнейшей единице, делящей нацело:
    # '60s' → '1min'; '15s' в минуты не делится → остаётся '15s'.
    assert st == "1min"
    assert idl == "15s"
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py::test_apply_timeouts_sets_session_guc -v`
Expected: FAIL — `ImportError`/`AttributeError`: `_apply_timeouts` ещё не существует. (Если нет `DATABASE_URL_TEST` — тест скипнется; тогда верификация переносится на CI/тест-ветку, отметить это в ревью.)

- [ ] **Step 3: Реализовать `_apply_timeouts`**

В `backend/app/seed/loader.py`, рядом с `_reset` (до `execute`), добавить:

```python
async def _apply_timeouts(conn: AsyncConnection) -> None:
    # Операционная страховка сессии сида (SET LOCAL — живёт только в этой транзакции).
    # ВНИМАНИЕ (инвариант): idle=15s безопасен ТОЛЬКО потому, что build_load
    # (весь парсинг Excel) в run() исполняется ДО begin() — внутри транзакции
    # клиентских пауз нет, лишь пайплайн вставок с мс-зазорами. Перенос парсинга
    # внутрь транзакции сделает 15s миной. statement_timeout де-факто сторожит
    # _reset (каскад DELETE) и freeze_release; для executemany в extended-протоколе
    # таймер гасится завершением каждого Execute (запас огромен). Значения —
    # литеральные константы (не пользовательский ввод), инъекции нет.
    await conn.execute(text("SET LOCAL statement_timeout = '60s'"))
    await conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = '15s'"))
```

- [ ] **Step 4: Подключить в `run()`**

В `backend/app/seed/loader.py` в функции `run` заменить блок записи:

```python
    async with get_engine().begin() as conn:
        await _apply_timeouts(conn)
        await execute(conn, plan, author=author, freeze=freeze, force=force)
```

- [ ] **Step 5: Прогнать тест — убедиться, что проходит**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py::test_apply_timeouts_sets_session_guc -v`
Expected: PASS (при наличии `DATABASE_URL_TEST`).

- [ ] **Step 6: Коммит**

```bash
git add backend/app/seed/loader.py backend/tests/db/test_seed_loader.py
git commit -m "feat(seed): _apply_timeouts (SET LOCAL statement/idle timeout) в run()"
```

---

### Task 2: Предвыделение id + батч category/position/vendor/agreement

Ядро декомпозиции для трёх RETURNING-таблиц. `listing` пока остаётся построчным (переводится в Task 3) — промежуточное состояние полностью рабочее, тесты зелёные.

**Files:**
- Modify: `backend/app/seed/loader.py` (добавить `_prealloc_ids`; переписать `execute` пп.3–7, кроме listing)
- Test: `backend/tests/db/test_seed_loader.py` (два новых теста-гварда)

**Interfaces:**
- Consumes: `_apply_timeouts` (Task 1) не нужен здесь напрямую (только в run).
- Produces: `async def _prealloc_ids(conn: AsyncConnection, table: str, n: int) -> list[int]` — возвращает `n` уникальных id из sequence таблицы (пустой список при `n == 0`).

- [ ] **Step 1: Написать тесты-гварды (вложенные категории + sequence-sync)**

В `backend/tests/db/test_seed_loader.py` добавить. Импорты `CategoryNode`, `PositionRow`, `ListingRow`, `LoadPlan`, `RunReport`, `execute`, фабрики `f` — уже есть в шапке файла.

```python
async def test_execute_nested_categories_resolve_parent(db_conn) -> None:
    # 2-уровневое дерево: parent_id ребёнка должен указывать на родителя.
    # Порядок executemany (родитель раньше) держит FK-валидность без DEFERRABLE.
    cats = [
        CategoryNode((1,), "Родитель", None, 0),
        CategoryNode((1, 1), "Ребёнок", (1,), 0),
    ]
    positions = [PositionRow(1, (1, 1), "Поз", None, 0)]
    listings = [
        ListingRow(1, "residential", "Бизнес", "not_applicable",
                   None, False, None, None, 0),
    ]
    report = RunReport(files=[], vendors_unique=0, agreements=0,
                       star_occurrences=0, categories=2, category_warnings=[])
    plan = LoadPlan(cats, positions, listings, {}, {"residential": None}, report)

    await execute(db_conn, plan, author="seed@test", freeze=False, force=False)

    parent_name = (await db_conn.execute(text(
        "SELECT p.name FROM category child "
        "JOIN category p ON p.id = child.parent_id "
        "WHERE child.name = 'Ребёнок'"))).scalar_one()
    assert parent_name == "Родитель"


async def test_execute_leaves_sequences_ahead(db_conn) -> None:
    # После вставки с ЯВНЫМИ id sequence должен быть «впереди»: вставка без явного
    # id (через фабрику) не должна словить PK-коллизию. Доказывает, что setval
    # добавлять НЕ нужно (id взяты из того же sequence через nextval).
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)

    v = await f.make_vendor(db_conn, name="Новый Вендор")
    cat = await f.make_category(db_conn, name="Новый Раздел")
    pos = await f.make_position(db_conn, category_id=cat, name="Новая Поз")
    assert v and cat and pos  # id присвоены из sequence, коллизии PK не было
```

- [ ] **Step 2: Прогнать db-набор на ТЕКУЩЕМ коде — базлайн зелёный**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -v`
Expected: все PASS, включая два новых (текущий построчный `execute` их удовлетворяет — это базлайн перед рефактором; sequence-sync проходит тривиально, т.к. сейчас id присваивает БД). Если скип по `DATABASE_URL_TEST` — перенос на CI.

- [ ] **Step 3: Добавить `_prealloc_ids`**

В `backend/app/seed/loader.py` рядом с `_reset`:

```python
async def _prealloc_ids(conn: AsyncConnection, table: str, n: int) -> list[int]:
    # Предвыделяем n id из sequence таблицы — вместо RETURNING (порядок строк в
    # INSERT ... RETURNING формально не документирован). Порядок возврата неважен:
    # нужны просто n уникальных значений. nextval НЕТРАНЗАКЦИОНЕН — при откате
    # значения «сгорают», дырки в id легальны. setval НЕ нужен: id взяты из этого
    # же sequence, поэтому он уже «впереди».
    if n == 0:
        return []
    rows = await conn.execute(
        text("SELECT nextval(pg_get_serial_sequence(:t, 'id')) "
             "FROM generate_series(1, :n)"),
        {"t": table, "n": n},
    )
    return [int(x) for x in rows.scalars().all()]
```

- [ ] **Step 4: Переписать `execute` пп.3–7 (кроме listing)**

В `backend/app/seed/loader.py` заменить тело `execute` от секции «3. Категории» до конца секции «5. Вендоры + соглашения» (пп.3–5 старого кода) на предвыделение + батчи. Секцию «1. Идентичность аудита» и «2. Защита + сброс» НЕ трогать. Секции «6. Карта сегментов» и «7. Листинги» и «8. freeze» пока оставить как есть (listing — Task 3).

Новый блок (вставляется сразу после `await _reset(conn)`):

```python
    # 3. Предвыделение id для таблиц, чьи id нужны downstream (документированно,
    #    без RETURNING). Порядок возврата неважен — раскладываем позиционно.
    vendor_names = list(plan.vendors)
    cat_ids = await _prealloc_ids(conn, "category", len(plan.categories))
    pos_ids = await _prealloc_ids(conn, "position", len(plan.positions))
    ven_ids = await _prealloc_ids(conn, "vendor", len(vendor_names))
    cat_id: dict[tuple[int, ...], int] = {
        node.number: cid for node, cid in zip(plan.categories, cat_ids)
    }
    pos_id: dict[int, int] = {
        pos.pos_key: pid for pos, pid in zip(plan.positions, pos_ids)
    }
    vendor_id: dict[str, int] = {
        name: vid for name, vid in zip(vendor_names, ven_ids)
    }

    # 4. Категории — один executemany с явным id + parent_id из карты.
    #    ВНИМАНИЕ: список параметров ОБЯЗАН идти родители-раньше-детей
    #    (plan.categories == tree.ordered()). asyncpg executemany выполняет наборы
    #    строго последовательно в порядке списка — это (а не DEFERRABLE) держит FK
    #    parent_id валидным построчно. НЕ переводить на multi-row VALUES / чанки /
    #    параллельные вставки — тихо сломается валидность родителей.
    if plan.categories:
        await conn.execute(
            text("INSERT INTO category(id, parent_id, name, sort_order) "
                 "VALUES (:id, :p, :n, :s)"),
            [{"id": cat_id[node.number],
              "p": cat_id[node.parent] if node.parent is not None else None,
              "n": node.name, "s": node.sort_order}
             for node in plan.categories],
        )

    # 5. Позиции — один executemany с явным id + category_id из карты.
    if plan.positions:
        await conn.execute(
            text("INSERT INTO position(id, category_id, name, source_ref, sort_order) "
                 "VALUES (:id, :c, :n, :sr, :s)"),
            [{"id": pos_id[pos.pos_key], "c": cat_id[pos.category_number],
              "n": pos.name, "sr": pos.source_ref, "s": pos.sort_order}
             for pos in plan.positions],
        )

    # 6. Вендоры — один executemany с явным id. Соглашения (звезда) — отдельный
    #    executemany по звёздным вендорам (свой id agreement downstream не нужен —
    #    остаётся на default sequence). agreement-change_log триггер сработает
    #    построчно и возьмёт автора из app.user (см. п.1).
    if vendor_names:
        await conn.execute(
            text("INSERT INTO vendor(id, name) VALUES (:id, :n)"),
            [{"id": vendor_id[name], "n": name} for name in vendor_names],
        )
    starred = [name for name, is_starred in plan.vendors.items() if is_starred]
    if starred:
        await conn.execute(
            text("INSERT INTO agreement(vendor_id, status) VALUES (:v, 'active')"),
            [{"v": vendor_id[name]} for name in starred],
        )
```

Убедиться, что старые секции «3/4/5» (построчные циклы категорий/позиций/вендоров с `RETURNING id`) удалены, а `seg_id`/listing/freeze ниже используют те же имена карт `cat_id`/`pos_id`/`vendor_id` (имена сохранены — ниже по коду правок не требуется).

- [ ] **Step 5: Прогнать db-набор — всё зелёное после рефактора**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -v`
Expected: все PASS (6 исходных + 2 новых). Идемпотентность и автор-через-триггер подтверждают, что батч-путь даёт идентичный результат.

- [ ] **Step 6: Коммит**

```bash
git add backend/app/seed/loader.py backend/tests/db/test_seed_loader.py
git commit -m "feat(seed): предвыделение id + батч category/position/vendor/agreement"
```

---

### Task 3: `listing` → executemany

Главный выигрыш (~13k строк). Валидация segment-ключа выносится в предпроход (нельзя валидировать «посреди» batch), затем один `executemany`.

**Files:**
- Modify: `backend/app/seed/loader.py` (секция «7. Листинги» в `execute`)

**Interfaces:**
- Consumes: карты `pos_id`, `vendor_id`, `seg_id` из ранее выполненных секций `execute`.
- Produces: (нет новых публичных имён).

- [ ] **Step 1: Убедиться, что listing-тесты сейчас проходят (базлайн)**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -v`
Expected: все PASS (после Task 2). Это база — Task 3 не должен ничего сломать.

- [ ] **Step 2: Переписать секцию listing на executemany**

В `backend/app/seed/loader.py` заменить построчный цикл `for ln in plan.listings:` (секция «7. Листинги») на предпроход-валидацию + один batch:

```python
    # 7. Листинги — предпроход собирает параметры и валидирует segment-ключ
    #    (нельзя валидировать посреди executemany), затем один batch. Триггеры
    #    listing_stamp/listing_audit/listing_cell_chk срабатывают построчно и при
    #    executemany — аудит и инвариант ячейки сохранены. Все dict'ы одной пачки
    #    имеют идентичный набор ключей (требование prepared statement).
    listing_params = []
    for ln in plan.listings:
        key = (ln.building_type, ln.segment_name)
        if key not in seg_id:
            avail = sorted(n for (c, n) in seg_id if c == ln.building_type)
            raise SeedError(
                f"Класс {ln.segment_name!r} ({ln.building_type}) не найден в segment. "
                f"Доступны: {avail}"
            )
        listing_params.append(
            {"p": pos_id[ln.pos_key], "seg": seg_id[key],
             "v": vendor_id[ln.vendor_name] if ln.vendor_name else None,
             "st": ln.status, "spec": ln.spec_text, "ujin": ln.ujin,
             "note": ln.note, "so": ln.sort_order}
        )
    if listing_params:
        await conn.execute(
            text("INSERT INTO listing(position_id, segment_id, vendor_id, status, "
                 "spec_text, ujin_integration, note, sort_order) "
                 "VALUES (:p, :seg, :v, :st, :spec, :ujin, :note, :so)"),
            listing_params,
        )
```

- [ ] **Step 3: Прогнать db-набор — всё зелёное**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -v`
Expected: все PASS. Особенно `test_execute_is_idempotent` (повтор не плодит строки) и `test_execute_loads_and_attributes_author` (автор через триггер на batch-listing).

- [ ] **Step 4: Юнит-тесты loader (DB-free) не задеты**

Run: `cd backend; uv run pytest tests/test_seed_loader.py -v`
Expected: все PASS (`build_load` не менялся).

- [ ] **Step 5: Коммит**

```bash
git add backend/app/seed/loader.py
git commit -m "feat(seed): listing → executemany (~13k строк одним пайплайном)"
```

---

### Task 4: TECH_DEBT + финальный `just ci`

Зафиксировать единственный осознанно непокрытый остаток и прогнать полный CI перед PR.

**Files:**
- Modify: `docs/TECH_DEBT.md` (секция «Сид-импорт Excel (разовый)»)

- [ ] **Step 1: Добавить строку в TECH_DEBT**

В `docs/TECH_DEBT.md` в секцию «## Сид-импорт Excel (разовый)» добавить последним пунктом:

```markdown
- **Эффект таймаутов сида не покрыт автотестом.** `_apply_timeouts` ставит
  `statement_timeout`/`idle_in_transaction_session_timeout`; тест проверяет их
  ПРИМЕНЕНИЕ через `SHOW` (ловит ошибку единиц измерения), но реальный обрыв по
  таймауту не воспроизводится без медленного оператора (`pg_sleep`) — сознательно
  не тестируем. Эффект верифицируется инспекцией.
```

- [ ] **Step 2: Полный локальный CI**

Run: `just ci`
Expected: зелёно — types, lint/ruff, mypy `app`, backend pytest (+db на Neon, если доступна), frontend vitest. Если db-тесты скипаются локально (нет `DATABASE_URL_TEST`) — они отработают на эфемерной Neon в CI после пуша.

- [ ] **Step 3: Коммит**

```bash
git add docs/TECH_DEBT.md
git commit -m "docs(seed): отметить непокрытый автотестом эффект таймаутов в TECH_DEBT"
```

- [ ] **Step 4: Пуш + PR**

```bash
git push -u origin feat/seed-writepath-decomposition
gh pr create --base main --title "feat(seed): декомпозиция записи (batch executemany + timeouts)" --body "См. спеку docs/superpowers/specs/2026-07-09-seed-writepath-decomposition-design.md и план docs/superpowers/plans/2026-07-09-seed-writepath-decomposition.md. Минуты → секунды, атомарность §14 и инварианты db-тестов сохранены."
```

Дождаться зелёного CI (db-тесты на эфемерной ветке Neon), затем ревью/мерж.

---

## После мержа (не задача плана — по памяти проекта)

- **Девлог:** `docs/devlog/` — файл на задачу (`2026-07-09-seed-writepath-decomposition.md` или дополнение к существующему сид-девлогу). Зафиксировать **замер реального прогона** (было минуты → стало N секунд) с первого боевого/тест-веточного запуска — подтвердить заявленную цель числом.
- Сверить CLAUDE.md §5 (упоминание сида) — при необходимости обновить формулировку.
