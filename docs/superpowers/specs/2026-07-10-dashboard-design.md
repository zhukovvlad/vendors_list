# Дизайн: дашборд «Обзор» (начальный экран, read-only)

**Дата:** 2026-07-10
**Статус:** на ревью
**Ветка:** `feat/dashboard-overview`
**Фаза:** 1 (ведение вендор-листов). Без проектов и светофора.

## Цель

Начальный экран приложения — сводка по каталогу стандартов: три метрики
(**Позиции / Издания / Вендоры**), список **черновиков в работе** и очередь
**«Требует внимания»**. Экран строго read-only: показывает состояние, не меняет
его. Действия (создать стандарт, войти в редактор, объединить вендоров) ведут в
экраны будущих срезов — в этом срезе их цели ещё не построены (см. §«Вне объёма»).

Макет: `dashboard_phase1_clean_v4.html` (тёмная тема; значения-заглушки).

## Терминология и подтверждённые факты схемы

Сверено по [0001_core_schema.sql](../../../backend/migrations/sql/0001_core_schema.sql).
Это отменяет несколько имён из стартовой инструкции, которые в схеме не существуют.

| Понятие | Факт в схеме |
|---|---|
| **«Стандарт»** | Это `building_type` (residential/office/social, 3 строки). Таблицы `standard`/колонки `standard_id` **нет**. Вендор-лист привязан к типу объекта. |
| **Издание** | Строка `release`. `status` ∈ `open` (**черновик**) / `published` (**релиз**) / `archived`. |
| **«Выпустить релиз»** | Функция `freeze_release()` ([:360](../../../backend/migrations/sql/0001_core_schema.sql#L360)) — копирует живое состояние в неизменяемый снимок `release_listing`, ставит `status='published'`, `frozen_at=now()`. |
| **Один черновик на тип** | `uq_release_one_open` ([:320](../../../backend/migrations/sql/0001_core_schema.sql#L320)) — максимум один `open` на `building_type` ⇒ черновиков физически ≤ 3. |
| **Мягкое удаление** | Только на `listing` (`deleted_at`, [:183](../../../backend/migrations/sql/0001_core_schema.sql#L183)). У `position`/`vendor` его нет — «живость» позиции определяется наличием живых строк `listing`, а не флагом на позиции. |
| **Соглашение (звезда)** | `agreement.status='active'` → функция `vendor_starred()` ([:122](../../../backend/migrations/sql/0001_core_schema.sql#L122)). |
| **Бренд-ключ** | `coalesce(vendor.represents_id, vendor.id)` — известное владение брендом («ИСТРАТЕХ (Grundfos)» → Grundfos). |

## Где живёт логика (тест ТЗ §6)

- **Счётные агрегаты и списки** (метрики, счётчики изданий/вендоров, черновики,
  «залежался») — вычисляемые истины → **вьюхи БД**, по образцу
  `compliance.project_summary`. API читает готовое, не пересчитывает.
- **Детект похожих вендоров** (кандидаты на объединение) — прикидочная эвристика,
  а нормализация/схлопывание брендов у нас живёт в **прикладном слое**, не в БД.
  → считает **бэкенд**. Это единственная неточная величина на экране, помечается как
  «прикидка».

## Метрики (финальный состав)

### 1. Позиции — «в действующих релизах»

Вариант **A (из снимка)**. Для каждого `building_type` берём **последний
`published` `release`**, считаем уникальные позиции его снимка:

```sql
WITH current_release AS (
    SELECT DISTINCT ON (building_type_id) id
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC          -- PK-страховка: тотальный детерминизм
)
SELECT count(DISTINCT rl.position_id)
FROM release_listing rl
JOIN current_release cr ON cr.id = rl.release_id
WHERE rl.position_id IS NOT NULL;
```

`id DESC` в хвосте обязателен: `effective_date` nullable, уникальности на
`published`-релизы нет — без `id` «последний» недетерминирован при равных датах.
Снимок иммутабелен ⇒ число стабильно и совпадает с матрицей каталога (тот же мир
снимков), не «дышит» от правок черновика.

### 2. Издания — всего, с делением

```sql
SELECT count(*) FILTER (WHERE status = 'published') AS releases_published,
       count(*) FILTER (WHERE status = 'open')      AS drafts_open
FROM release;
```

Заголовок «21» = `releases_published + drafts_open`. `archived` в срезе не
используется (функция `freeze_release` его не ставит) — **исключаем** из счётчиков
(развилка O5).

### 3. Вендоры — всего, с соглашением, кандидаты на объединение

Грань — **бренд-ключ** (развилка O1):

```sql
WITH brands AS (SELECT DISTINCT coalesce(represents_id, id) AS brand_id FROM vendor)
SELECT count(*) AS vendors_total,
       count(*) FILTER (WHERE vendor_starred(brand_id)) AS vendors_with_agreement
FROM brands;
```

`vendors_with_agreement` — у **владельца бренда** есть active-agreement (§4 «судим
по владельцу бренда»). `merge_candidate_pairs` — отдельно, из бэкенда (см. §Детект).

## Панели

### «Черновики в работе» — список открытых черновиков по свежести

Без прогресса/готовности (выкинуты). Открытый черновик = `release.status='open'`;
его содержимое — живое состояние `listing` этого `building_type` (freeze потом снимет
именно его). «Тронут» = последняя правка живого перечня типа:

```sql
-- вьюха dashboard_open_drafts (одна строка на открытый черновик, ≤ 3)
SELECT r.id                         AS release_id,
       r.building_type_id,
       bt.name                      AS building_type_name,
       r.label,
       coalesce(la.last_at, r.created_at)     AS last_touched_at,
       coalesce(la.last_by, r.author)         AS last_touched_by
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
```

Имя строки экрана = `building_type_name · label` (версия «v4» закодирована в `label`;
отдельной колонки версии в схеме нет). Относительное время («изменён вчера») и
подпись `· вами` — форматируются на фронте из `last_touched_at`/`last_touched_by`.
Сортировка — `last_touched_at DESC`.

### «Требует внимания» — только реальные задачи

Композиция на фронте из уже загруженных данных, без отдельного эндпоинта:

1. **Кандидаты на объединение** — `summary.merge_candidate_pairs` (прикидка, бэкенд).
   Одна строка-подсказка «N пар вендоров похожи».
2. **Залежавшийся черновик** — черновик из `dashboard_open_drafts`, у которого
   `last_touched_at < now() - interval '14 days'` (порог O6). Мягкая подсказка, не
   приговор. Пустых ячеек здесь нет — это валидное состояние стандарта.

## Детект кандидатов на объединение (бэкенд, прикладной слой)

Консервативная высокоточная эвристика (развилка O3): **коллизия нормализованного
имени** между разными бренд-ключами. Нормализация — та же, что зреет для гигиены
справочника: lower, схлопнуть пробелы/пунктуацию, убрать хвосты вида `(Native)`.
Две записи с равной нормой, но разными `coalesce(represents_id, id)` и не связанные
через `vendor_alias`, — кандидат-пара. Триграммный fuzzy-порог — **отложен**
(TECH_DEBT): даёт шум и требует калибровки на реальных данных.

`merge_candidate_pairs` = число таких пар. Функция бэкенда `count_merge_candidates()`
(read-only). Дорастёт до полноценного экрана гигиены в отдельном срезе.

## Контракт API

Один агрегирующий эндпоинт — один экран, один round-trip. Чтение,
`Depends(require_user)` + `read_conn` (паттерн `meta.py`/`releases.py`).

```
GET /dashboard  ->  Dashboard
```

```python
class DashboardSummary(BaseModel):
    positions_active: int          # вьюха dashboard_summary
    releases_published: int
    drafts_open: int
    vendors_total: int             # бренд-ключ
    vendors_with_agreement: int
    merge_candidate_pairs: int     # бэкенд, ПРИКИДКА

class DashboardDraft(BaseModel):
    release_id: int
    building_type_name: str
    label: str
    last_touched_at: datetime
    last_touched_by: str | None
    is_stale: bool                 # last_touched_at < now() - 14d

class Dashboard(BaseModel):
    summary: DashboardSummary
    drafts: list[DashboardDraft]   # открытые черновики по свежести, ≤ 3
```

`is_stale` считается в SQL (порог-константа документирована), чтобы «залежался»
был единой истиной, а не дублировался на фронте. «Требует внимания» фронт собирает
из `summary.merge_candidate_pairs` + `drafts.filter(is_stale)`.

Скалярные счётчики — из новой вьюхи `dashboard_summary` (одна строка); список
черновиков — из `dashboard_open_drafts`; `merge_candidate_pairs` — из бэкенд-функции.

### Миграция

Новая Alembic-ревизия **чистым SQL** (`just makemigration` + `op.execute`); базовый
`0001` неизменен (CLAUDE.md §5). Создаёт вьюхи `dashboard_summary` и
`dashboard_open_drafts` (+ `downgrade` их снимает). Инвариантов не добавляет —
только read-проекции.

## Дизайн-система: статус-токены как PR-предшественник

Отдельный маленький PR **до** дашборда (как делали фундамент под `button`), чтобы
экран потреблял готовые токены, а не тащил DS-правки внутри фичи. §5 требует красить
статусы через `text-success`/`text-warning`/`text-danger-state`, но в
[index.css](../../../frontend/src/index.css) есть только `--destructive`. Danger уже
закрыт (`--destructive`/`--destructive-solid`); заводим **success** и **warning**
bridge-токенами тем же паттерном:

```css
:root { --success: #158173; --warning: #9A6636; }          /* светлая */
.dark { --success: #82D6CC; --warning: #BD9375; }          /* тёмная  */
/* @theme inline */
--color-success: var(--success);
--color-warning: var(--warning);
```

Значения совпадают с палитрой чартов (`--chart-2`/`--chart-3`) — согласованы. На
дашборде сейчас нужен **warning** (тановый «залежался»/«черновик» — вместо сырого
`--color-tan`, что §5 в компонентах запрещает); **success** заводим как фундамент
для будущих позитивных статусов. Реколор через переменные shadcn, без второго набора,
без хардкода. Vitest на утилиты токенов. Это фронт-изменение ⇒ гоняем `just ci`.

## Фронтенд

- **Роут (развилка O2):** дашборд — начальный экран `/`; матрицу переносим на
  `/matrix`; `/design-system` без изменений. Правим [router.tsx](../../../frontend/src/router.tsx)
  (code-based дерево TanStack Router; `routeTree` по-прежнему экспортируется для тестов).
- **Экран** `screens/dashboard/DashboardScreen.tsx` + `model.ts` (чистые хелперы:
  относительное время, форматирование чисел, вывод «залежался»). Таблиц нет —
  `columns` не нужен. Структура — как у `screens/matrix/`.
- **Данные:** хук `useDashboard()` в [queries.ts](../../../frontend/src/api/queries.ts)
  поверх типизированного клиента; форма из OpenAPI → `schema.d.ts` (`just types`).
- **DS:** карточки (`card`) и бейджи (`badge`) уже есть с матрицы; иконки — `lucide-react`
  (в зависимостях). Новых DS-примитивов, кроме статус-токенов выше, не требуется.
- **Действия отложены (развилка O4):** «Новый стандарт», шевроны черновиков и очереди
  внимания рендерятся, но в этом срезе **инертны/выключены** — их цели (редактор
  издания, экран объединения вендоров) строятся будущими срезами. Помечаем видимой
  «заглушкой», не мёртвой ссылкой.
- **Локализация — только русская.**
- **Пустые состояния:** нет черновиков → пустой список; свежая БД без релизов →
  метрики нули, экран не падает.

## Тесты (red → green)

**Backend** (`pytest` + фабрики, маркер `db` на тест-ветке Neon):
- `dashboard_summary`: `positions_active` из снимка последнего `published` на тип;
  **детерминизм** «последнего» при равных `effective_date` (страховка `id`);
  бренд-ключ схлопывает `represents_id`; `vendors_with_agreement` по владельцу бренда;
  счётчики изданий по `status`, `archived` исключён.
- `dashboard_open_drafts`: ≤ 1 открытый на тип; `last_touched_at` из живого `listing`
  (fallback на `release.created_at`); `is_stale` по порогу 14 дней.
- `count_merge_candidates`: коллизия нормы между разными бренд-ключами даёт пару;
  связанные через `vendor_alias`/`represents_id` — не дублируются.
- api-тест через ASGI-`client`: форма `GET /dashboard`, `require_user`.

**Frontend** (Vitest + MSW под сгенерированную схему):
- три карточки с числами; список черновиков по свежести; «Требует внимания» =
  кандидаты + залежавшиеся; относительное время из `model.ts`; пустые состояния;
  дашборд рендерится как `/`.

## Развилки (решения, помечены как открытые для ревью)

| # | Развилка | Решение | Статус |
|---|----------|---------|--------|
| O1 | Грань «Вендоров» | **Бренд-ключ** `count(distinct coalesce(represents_id,id))`; «с соглашением» по владельцу бренда | **допущение** — подтвердить/сменить на сырой `count(vendor)` |
| O2 | Роут начального экрана | Дашборд `/`, матрица → `/matrix` | подтвердить |
| O3 | Эвристика дублей | Консервативная коллизия нормы; триграммы отложены | подтвердить |
| O4 | Действия/навигация | Отрисованы, но инертны (цели — будущие срезы) | подтвердить |
| O5 | `archived`-издания | Исключены из счётчиков | подтвердить |
| O6 | Порог «залежался» | 14 дней | подтвердить |

## Порядок слайсов (бисектабельно, CI зелёный на каждом)

1. **PR-предшественник:** статус-токены `success`/`warning` в `index.css` + vitest.
   `just ci`.
2. Миграция: вьюхи `dashboard_summary` + `dashboard_open_drafts` + db-тесты.
3. Бэкенд: `count_merge_candidates()` + эндпоинт `GET /dashboard` (схемы + роутер) +
   db/api-тесты; `just types`.
4. Фронт: роут `/` (дашборд) + перенос матрицы на `/matrix`; экран + `model.ts` +
   `useDashboard`; Vitest/MSW.
5. `just ci` зелёный; devlog; обновить CLAUDE.md §5 (новый экран) и TECH_DEBT
   (триграммный fuzzy-детект).

## Вне объёма

- Проекты, светофор, проверка соответствия (фаза 2).
- Любые пишущие эндпоинты и мутации (экран read-only): «Новый стандарт», фиксация
  релиза с дашборда, объединение вендоров.
- Экраны-цели навигации (редактор издания, гигиена/объединение вендоров, список
  вендоров) — отдельные срезы.
- Триграммный/fuzzy-порог детекта дублей (TECH_DEBT).
- Импорт/экспорт Excel, админ-редактирование.
- Дублирование бизнес-логики БД в коде; ORM; правка базового `0001`.

## TECH_DEBT (внести при реализации)

- **Триграммный детект дублей** — v1 ловит только коллизии нормализованного имени;
  похожие-но-не-равные (опечатки за порогом нормы) не найдёт.
- **Стоимость `merge_candidate_pairs` в общем payload** — если детект на реальных
  данных окажется тяжёлым, вынести в отдельный ленивый эндпоинт, чтобы метрики и
  черновики красились мгновенно.
