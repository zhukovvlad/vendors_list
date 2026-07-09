# Дизайн: матрица перечня (первый продуктовый экран, read-only)

**Дата:** 2026-07-09
**Статус:** утверждён к реализации
**Ветка:** `feat/listing-matrix`
**Ревизии:** r1 — первичный дизайн (5 развилок §2); r2 — правки ревью (`category_sort_path`
вместо текстовой сортировки, дефолт в loader'е, `note` per-vendor); r3 — SQL-выборка
(CTE `pos_page`/`cats`, `DISTINCT position_id`, тип `category_path: str`, семантика `q`);
r4 — стык `q`×`segment_id` и подпись `total` при сужении. «Утверждён» относится к
текущему телу (r4).

## Цель

Реализовать **матрицу перечня** — главный read-only экран (ТЗ §4.1): строки —
позиции по дереву разделов, колонки — классы (`segment`) выбранного типа объекта,
в ячейках — вендоры позиции в этом классе (звезда `vendor_starred` = действующее
соглашение) либо текстовое требование (`spec_text`) / прочерк. Первый настоящий
продуктовый экран: сейчас `App.tsx` — только витрина дизайн-системы, роутинга и
продуктовых экранов нет.

## Контекст

**Данные — вьюха `listing_live`** ([0001_core_schema.sql:407](../../../backend/migrations/sql/0001_core_schema.sql#L407)):
плоские строки, одна строка = один listing-ряд на `(position × segment)`. Ряд —
это либо **вендор** (`vendor_id` задан, `vendor_name`, `vendor_starred`,
`ujin_integration`, `note`), либо **требование** (`vendor_id NULL`, `spec_text` =
«Россия»/ГОСТ/«по согласованию», плюс `note`). Инвариант БД запрещает смешивать в
одной ячейке вендоров и требование. Звезда/статусы уже вычислены в БД — читаем как
есть, не пересчитываем (CLAUDE.md §2, ТЗ §6).

**Что уже есть:**
- [`GET /listings`](../../../backend/app/routers/listings.py) — **плоские** ряды
  `listing_live`, фильтры `segment_id`/`position_id`/`q`, `LIMIT/OFFSET` по рядам.
- [`GET /meta/building-types`, `GET /meta/segments`](../../../backend/app/routers/meta.py)
  — справочники для фильтров/колонок.
- Фронт: типизированный клиент [`client.ts`](../../../frontend/src/api/client.ts)
  (OpenAPI → `schema.d.ts`), хук `useListings` в [`queries.ts`](../../../frontend/src/api/queries.ts),
  TanStack Query подключён; TanStack Table — нет; DS-компонентов кроме `button` нет.
- `category`/`position` имеют кураторский `sort_order` (виден в `seed/loader.py`),
  `category_path(id)` — рекурсивная функция текстового пути.

## Развилки и решения (зафиксированы в брейншторме)

| # | Развилка | Решение | Обоснование |
|---|----------|---------|-------------|
| §2.1 | Pivot vs серверная пагинация | **Server pivot, пагинация по позициям**; новый эндпоинт `GET /listings/matrix`, шейпинг в Python-роутере над `listing_live`, **без новой вьюхи**; ячейки — **массив** | Плоский `LIMIT/OFFSET` рвёт ячейки позиции по страницам. Пагинация по позиции делает «строка не рвётся» структурным свойством. Форма, которую рендерит фронт, живёт в типизированном контракте (OpenAPI→TS, проверяется MSW). Ячейки массивом (не map) — чтобы `openapi-typescript` не выродил их в `additionalProperties`. Pivot — презентационная проекция, а не инвариант → место в API, не в схеме (ТЗ §6) |
| §2.2 | Группировка колонок | Дерево колонок **в payload** (`columns:[{group, segments[]}]`), в TanStack Table — `columnHelper.group` | Матрица per-building-type: колонки и ячейки обязаны совпадать 1-в-1 → самодостаточный payload гарантирует консистентность |
| §2.3 | Дерево разделов в строках | **Плоские строки-заголовки** по `category_path` (полный путь), без сворачивания в v1 | Сворачиваемые узлы конфликтуют с серверной пагинацией (меняют «что на странице»). Сворачивание → TECH_DEBT |
| §2.4 | Роутер | **TanStack Router** | Фильтры (`building_type_id`, `segment_id`, `q`, `offset`) — типизированный URL-контракт состояния экрана (расшариваемая ссылка, back, reload). Растёт на модуль соответствия/проекты. Родная интеграция с TanStack Query/Table |
| §2.5 | Срез DS-компонентов | `table`/`badge`/`card` **этим же PR, первыми слайсами**, только эти три | Прямая зависимость экрана (TECH_DEBT). Матрица — первый нагруженный потребитель → компоненты сразу проверяются боем, а не подгоняются под догадку. Слайсы бисектабельны, CI зелёный на каждом коммите |

## Контракт эндпоинта `GET /listings/matrix`

**Query params** (переиспользуют имена `/listings`; `building_type_id` — новый первичный):

| Параметр | Тип | Смысл |
|----------|-----|-------|
| `building_type_id` | `int` **(обязателен)** | определяет колонки и какую матрицу |
| `segment_id` | `int \| None` | сузить до одного класса (одна колонка) |
| `q` | `str \| None` | поиск по позиции/вендору/`category_path` (тот же ILIKE) |
| `limit` | `int = 50` (ge=1, le=200) | **позиций** на страницу |
| `offset` | `int = 0` (ge=0) | смещение по позициям |

**Response `Matrix`** (Pydantic, ячейки — массив; всё из `listing_live` как есть):

```python
class MatrixVendorRef(BaseModel):
    vendor_id: int
    name: str
    starred: bool              # = vendor_starred, как есть
    ujin_integration: bool
    note: str | None           # per-vendor (атрибут ряда)

class MatrixCell(BaseModel):
    segment_id: int
    vendors: list[MatrixVendorRef]   # непусто ⇒ вендорная ячейка
    spec_text: str | None            # требование (vendor NULL)
    note: str | None                 # значим ТОЛЬКО для ячейки-требования; для вендорной = None

class MatrixRow(BaseModel):
    position_id: int
    position_name: str
    category_path: str               # НЕ | None: position.category_id NOT NULL (0001:80) ⇒ путь всегда есть
    cells: list[MatrixCell]          # только сегменты, где у позиции есть ряд; отсутствие ⇒ "—"

class SegmentRef(BaseModel):
    id: int
    name: str
    sort_order: int

class SegmentGroupRef(BaseModel):
    id: int
    name: str

class MatrixColumnGroup(BaseModel):
    group: SegmentGroupRef | None    # None ⇒ плоские leaf-колонки (жилые/социальные)
    segments: list[SegmentRef]

class Matrix(BaseModel):
    columns: list[MatrixColumnGroup]
    items: list[MatrixRow]
    total: int                       # число РАЗЛИЧНЫХ позиций под фильтром
    limit: int
    offset: int
```

**Правила рендера ячейки (фронт):** `vendors` непусто → чипы вендоров (звезда для
`starred`, маркер Ujin для `ujin_integration`); иначе `spec_text` → текст/бейдж;
иначе `—`. `note` вендора — вторичный текст у чипа; `cell.note` — у требования.

## Выборка (шейпинг в Python-роутере, две read-проекции + колонки)

Все запросы — сырой SQL через SQLAlchemy Core (без ORM), только чтение.

1. **Страница позиций** — различные позиции под фильтром, в **кураторском** порядке.
   Отбор `DISTINCT` — по **одной колонке** `position_id` (не по кортежу: иначе, если
   `listing_live` начнёт менять состав, `DISTINCT` тихо размножит строки). Ключи
   сортировки (`csp`, текстовый путь) считаются **один раз на различную категорию**
   в CTE — рекурсивных вызовов O(различные категории), а не O(listing-ряды):
   ```sql
   WITH pos_page AS (
       SELECT DISTINCT ll.position_id
       FROM listing_live ll
       WHERE ll.segment_id IN (SELECT id FROM segment WHERE building_type_id = :bt)
         [AND ll.segment_id = :seg]
         [AND (ll.position_name ILIKE :q OR ll.vendor_name ILIKE :q OR ll.category_path ILIKE :q)]
   ),
   cats AS (   -- функции-пути ОДИН раз на категорию, не на позицию/ряд
       SELECT DISTINCT p.category_id,
              category_sort_path(p.category_id) AS csp,
              category_path(p.category_id)      AS cpath
       FROM pos_page pp JOIN position p ON p.id = pp.position_id
   )
   SELECT p.id AS position_id, p.name AS position_name, c.cpath AS category_path,
          c.csp, p.sort_order
   FROM pos_page pp
   JOIN position p ON p.id = pp.position_id
   JOIN cats c     ON c.category_id = p.category_id
   ORDER BY c.csp, p.sort_order, p.id           -- csp: int[] preorder, сравнение поэлементно
   LIMIT :limit OFFSET :offset
   ```
   `total` — `count(*)` из `pos_page` (те же различные позиции, без `LIMIT`).
   `position.category_id NOT NULL` ⇒ `csp`/`cpath` всегда заданы, `NULLS LAST` не нужен.
2. **Ячейки страницы** — все ряды `listing_live` для этих `position_id` под фильтром
   `building_type` (+`segment_id` если сужено), **без `q`**: поиск отбирает, *какие
   позиции* показать, но строка позиции отдаётся **целиком** (иначе матрица порвётся).
   Группировка в `MatrixRow.cells` (по `position_id` → `segment_id`) — в Python.
3. **Колонки** — сегменты `building_type` (+`segment_id` если сужено) с их
   `segment_group`, порядок `group.sort_order, segment.sort_order`, свёрнутые в
   `MatrixColumnGroup` (сегменты без группы → `group=None`).

**Семантика `q` (зафиксировать, не «чинить»):** `q` фильтрует **только шаг 1** —
отбирает позиции, у которых под текущим фильтром сегментов есть совпадение по
`position_name`/`vendor_name`/`category_path`. Совпадение по `vendor_name` означает
«показать позицию целиком, раз вендор встречается хоть в одном её классе», а не
«подсветить ячейки с вендором» — подсветки совпавших ячеек в v1 **нет**. Шаг 2
намеренно **не** применяет `q`; фильтровать его по `q` = порвать строку.

**Стык `q` × `segment_id` (явный случай для теста):** оба условия в `pos_page`
действуют на **одну строку** `listing_live`. Значит при заданном `segment_id`
позиция, прошедшая `q` по `category_path`/`position_name`, но **не имеющая ряда в
суженном сегменте**, в выдачу **не попадёт** (нет строки, где `segment_id = :seg` и
матч `q` одновременно). Это желаемо: в выбранном классе показывать нечего. db-тест
на `segment_id`+`q` обязан закрепить именно это (позиция без ряда в классе —
отсутствует), а не наткнуться на него случайно.

### Миграция: `category_sort_path(category_id) RETURNS int[]`

Блокер сортировки: `ORDER BY category_path` (текст) ломает кураторский порядок —
алфавит вместо `sort_order` (напр. «Вентиляция» < «ОВиК» вопреки курации), а дерево —
preorder-обход, одной текстовой строкой невыразим. `listing_live` не отдаёт ключи
сортировки (`l.sort_order` — порядок вендоров *внутри* ячейки).

Решение schema-first: функция-близнец `category_path` — тем же рекурсивным CTE
собирает `sort_order` предков в `int[]` (preorder-массив; сравнение массивов в
Postgres поэлементно-лексикографично). **Новой Alembic-ревизией чистым SQL**
(`just makemigration name="category_sort_path"` + `op.execute`); базовый `0001`
неизменен (CLAUDE.md §5). Это порядок отображения — презентация, инвариант не трогаем,
звезду/светофор не пересчитываем. Первый бэкенд-слайс.

## Фронтенд

### Роутинг (TanStack Router)

- Маршруты: `/` → экран матрицы; `/design-system` → текущая витрина из `App.tsx`
  (перенести в отдельный компонент, **не удалять**). Корневой layout.
- `validateSearch` (Zod): `building_type_id?` (**опционален**), `segment_id?`, `q?`,
  `offset` (default 0). Дефолт `building_type_id` **невыразим в validateSearch**
  (синхронный, а «первый тип» приходит из `/meta/building-types` асинхронно) →
  проставляется в **loader'е маршрута** редиректом на `?building_type_id=…` после
  резолва списка типов. Пустой список типов (свежая БД) → пустое состояние, не
  падение фетча.

### Данные / компоненты экрана

- Хук `useMatrix(params)` в [`queries.ts`](../../../frontend/src/api/queries.ts) поверх
  клиента; `useBuildingTypes`/`useSegments` для фильтров (эндпоинты `/meta/*` есть).
- TanStack Table: колонки из `columns` payload (`columnHelper.group` для сегментов с
  группой, плоские leaf для `group=None`); row model — `items`; **строка-заголовок
  раздела** инъектируется на смене `category_path` (spanning-ряд, печатает полный путь).
  **Решение (не баг):** раздел, попавший на границу страниц, печатает заголовок на
  обеих (конец стр. N и начало стр. N+1) — это желаемо, даёт контекст на новой странице.
- Ячейка: вендоры → `Badge`-чипы (звезда для `starred`, маркер Ujin), требование →
  текст/`Badge`, пусто → `—`. Поиск — с дебаунсом, пишет в URL.
- Серверная пагинация: контролы меняют `offset` в URL. `limit` ≤ 200 позиций; помни
  верхнюю границу payload: 200 × сегменты × вендоры-в-ячейке (на офисе крупнее) —
  не блокер на v1, но потолок известен.
- **Подпись счётчика:** при заданном `segment_id` `total` = «позиций **в классе X**»
  (`pos_page` включает `AND segment_id = :seg`), не «позиций всего». Счётчик подписать
  соответственно — иначе при переключении класса `total` прыгает и читается как баг.

### Срез DS-компонентов (первые слайсы, только эти три)

`table`, `badge`, `card` на DS-токенах (shadcn-примитивы + реколор через переменные
shadcn), каждый со своим vitest. Ничего сверх нужного матрице. Ожидаемые болячки
реколора: ховеры, бейджи-статусы, заголовки таблиц (TECH_DEBT).

## Тесты (red→green)

**Backend** (`pytest` + фабрики, маркер `db` на тест-ветке Neon):
- db-тест `category_sort_path`: preorder-массив, кураторский порядок ≠ алфавитному.
- db-тест `/listings/matrix`: пагинация по позициям не рвёт строку; звезда как есть;
  группировка колонок офиса (две группы) vs жилых (плоские); `total` = различные
  позиции; `q` отбирает позиции, но возвращает полную строку; `segment_id` сужает
  колонки; ячейка с `spec_text` (vendors пуст); пустая ячейка отсутствует в `cells`;
  `note`/`ujin_integration` per-vendor.
- api-тест через ASGI-`client` (форма ответа, коды, обязательность `building_type_id`).

**Frontend** (Vitest + MSW под сгенерированную схему):
- грид рендерится; групповые шапки колонок; маркер звезды; ячейка-требование; `—`;
  строки-заголовки разделов на смене `category_path`; фильтры/поиск меняют
  search-params; серверная пагинация; пустое состояние при отсутствии типов.

## Порядок слайсов (бисектабельно, CI зелёный на каждом)

1. Миграция `category_sort_path` + db-тест.
2. Эндпоинт `/listings/matrix` (схемы + роутер + выборка) + db/api-тесты; `just types`.
   **Перформанс — часть слайса, не отложено:** выборка шага 1 обязана считать
   `csp`/путь один раз на различную категорию (CTE выше), а не тянуть `category_path`
   из `listing_live` (та считает рекурсию на каждый listing-ряд под фильтром). Иначе
   первый же реальный сид тормозит, и это спишут на архитектуру. db-тест фиксирует
   форму запроса (одна `pos_page`-CTE, `DISTINCT position_id`).
3. DS-компоненты `table`/`badge`/`card` + vitest.
4. Роутинг (TanStack Router) + перенос витрины DS на `/design-system`.
5. Экран матрицы (фильтры, дерево-заголовки, ячейки, пагинация) + Vitest/MSW.
6. `just ci` зелёный; devlog; снять «Каталог компонентов» из TECH_DEBT; добавить
   заметку о рекурсивных `category_path`/`category_sort_path` (кандидат на
   материализацию при нагрузке).

## Вне объёма

- Модуль соответствия / светофор, карточки проектов, занесение выбора.
- Импорт/экспорт Excel, админ-редактирование перечня и изданий.
- Любые пишущие эндпоинты и мутации (экран строго read-only).
- Сворачиваемое дерево разделов (TECH_DEBT).
- Каталог DS сверх `table`/`badge`/`card`.
- Дублирование бизнес-логики БД; ORM; правка базового `0001`.

## TECH_DEBT (внести при реализации)

- **Сворачиваемое дерево разделов** — v1 показывает плоские строки-заголовки.
- **Рекурсивные `category_path`/`category_sort_path`.** v1 уже сводит вызовы к
  O(различные категории) на запрос (CTE `cats`). Долгосрочно, если и это станет
  узким местом на больших деревьях — материализация пути (доп. колонка на `category`
  с триггерным пересчётом / materialized view). Пока не требуется.
