# 2026-07-12 — Полиш блока «Где разрешён» (иерархия + правило «все классы»)

Ветка `feat/where-allowed-polish`, стекается на main (ветка `feat/vendor-card-polish` уже
слита, PR #21). Реализовано по методике subagent-driven-development
(спека [superpowers/specs/2026-07-12-where-allowed-polish-design.md](../superpowers/specs/2026-07-12-where-allowed-polish-design.md)):
4 задачи (Tasks 1–4), целевые срезы ревью между этапами.

Цель — переработать блок «Где разрешён» на карточке вендора: реализовать правило
«все классы» (helper + визуальная сводка), навести иерархию (кастомный Radix-триггер,
sunken полосы, guide line, легенда), снять визуальный симптом C2.

## Что сделано

### Этап 0: нулевой шаг (контракт)

**Находка:** payload эндпоинта `GET /vendors/{id}/where-allowed` не содержал знаменателя
для правила «все классы» — нужен счётчик разрешённых классов в каждом стандарте.
Нулевой шаг: миграция не нужна — знаменатель считается на уровне приложения одним
агрегатом, схему не трогаем.

- **Backend:** без новой ревизии Alembic. В `get_where_allowed` (роутер
  `backend/app/routers/vendors.py`) после сборки дерева из `vendor_where_allowed(:v)`
  выполняется один дополнительный запрос-агрегат
  `SELECT building_type_id, count(*) AS n FROM segment GROUP BY building_type_id`,
  результат раскладывается по `standards[i].segment_count`. SQL-функция
  `vendor_where_allowed` не тронута (source of truth не меняется), схема БД не меняется.
- **Фронт:** `just types` регенерирует `WhereAllowedStandard.segment_count: int` из
  обновлённой Pydantic-схемы (`backend/app/schemas/__init__.py`).
- **Тест-контракт:** api-тест обновлён, field присутствует в response.

### Task 1: контракт `segment_count` + `just types`

**Коммит `6a337fe`:** только router + schemas + тест, без миграций (`git show --stat`
подтверждает: `backend/app/routers/vendors.py`, `backend/app/schemas/__init__.py`,
`backend/tests/api/test_vendors.py` — три файла, ни одного в `migrations/`).
- Эндпоинт отдаёт `segment_count` per standard — прикладной агрегат по таблице
  `segment` (group by `building_type_id`), SQL-функция untouched.
- `OpenAPI schema` → `just types` → TypeScript типы `WhereAllowedStandard` готовы.
- api-тесты проходят; контракт верифицирован.

### Task 2: хелперы правила «все классы»

**Коммит `3542741`:** чистые функции в `frontend/src/screens/vendors/model.ts`.
- **`isAllClasses(position, segmentCount): boolean`** — для отдельной позиции:
  ```typescript
  excluded === 0 && allowed === segmentCount
  ```
  Guard: `segmentCount <= 0 → false` (деноминатор не валиден).
- **`standardAllClasses(standard): boolean`** — для standard объекта: непустой
  список позиций и КАЖДАЯ позиция даёт `isAllClasses(p, standard.segment_count)`
  (`standard.positions.every(...)`).
- **Тонкий кейс:** покрытие + несколько исключений = "все классы"? Нет —
  правило требует `excluded===0` (zero exceptions); открытый продуктовый вопрос
  (см. «Ловушки и уроки» ниже), не заведён в TECH_DEBT.
- Юнит-тесты: 5 кейсов (all, partial, none, boundary, invalid denominator).

### Task 3: переработка блока «Где разрешён»

**Коммит `cbe0927`:** переписание секции `VendorCardScreen.tsx` + интеграция хелперов.

#### Кастомный Radix-триггер

Вместо форка DS `Accordion` заново реализуем `AccordionPrimitive.Trigger` с нужными CSS:
```tsx
<AccordionPrimitive.Trigger className="...">
  <ChevronRight className="transition-transform group-data-[state=open]:rotate-90" />
  {title}
</AccordionPrimitive.Trigger>
```
- Leading chevron (вместо trailing shadcn-default) ротирует по `group-data-[state=open]`.
- Нет форка DS примитива (используем стандартный).

#### Иерархия (sunken-полосы + guide line)

- **Header** — полоса full-bleed с `bg-muted` (sunken вид). Механика без `-mx`-трюка:
  секция «Где разрешён» — единственная в карточке, где `CARD`-константа применена
  БЕЗ `px-5` (`className={\`${CARD} py-[15px]\`}`), а сам `px-5` расставлен точечно
  на внутренних блоках (заголовок блока, состояния загрузки/пусто). У `AccordionPrimitive.Trigger`
  свой `px-5`, но не отступ по бокам самой секции — поэтому полоса `bg-muted`
  дотягивается до краёв карточки естественно, без отрицательных отступов.
- **Guide line** — вертикальная линия слева (`ml-8 border-l border-border pl-4`)
  для визуальной иерархии листингов per-standard.
- **Dividers** между позициями — `divide-border/60` (тонкие, приглушённые).

#### "Все классы" rollup + summary

- **Заголовок (accordion header):** если `standardAllClasses(standard)`, к
  существующему тексту счётчика позиций дописывается `· все классы` (обычный
  текст-суффикс в том же `<span>`, не отдельный чип).
- **Per-position:** при развёртке позиция, для которой `isAllClasses(position,
  segmentCount)` истинно, вместо перечня чипов сегментов показывает один
  `<Badge variant="outline">все классы</Badge>`.

#### Тихая легенда

Внизу блока — borderless (без рамки-бокса) пояснение, показывается только когда
есть что объяснять (`hasExcludedChips(standards)`):
- Есть исключённые классы → ОДИН мини-образец чипа, borderless, с dashed-обводкой
  и strikethrough (`border-dashed border-border-strong px-1.5 line-through`),
  подписанный «класс», плюс текст «— был в последнем релизе, исключён · показано
  текущее состояние стандартов».
- Иначе (исключённых нет) → просто `whereAllowedLegend()`, т.е. текст
  «показано текущее состояние стандартов» без образца-чипа вовсе (нечего
  объяснять — на экране нет зачёркнутых чипов).
- Оба варианта — `text-caption text-muted-foreground`, без бордюра-рамки.

Никакой пары «зелёный заполненный / красный outline» и текста «зелёный —
разрешено, красный — исключение» в реализации нет: allowed-чипы не нуждаются
в пояснении (это дефолтное визуальное состояние), легенда объясняет только
неочевидный зачёркнутый случай.

#### Правило «все классы» вместо визуального симптома C2

Общий rollup `isAllClasses`/`standardAllClasses` (Task 2) заменяет перечень
чипов на бэдж «все классы», когда `excluded === 0 && allowed === segment_count`
— независимо от того, сколько сегментов у типа. Специального кейса
«`segmentCount === 1` → скрыть числа» в коде нет: для одноклассового типа
(«Социальные объекты», `segment_count = 1`) правило срабатывает тем же путём,
что и для многоклассовых — `isAllClasses` даёт `true` при покрытии единственного
сегмента, и вместо перечня чипов рисуется тот же бэдж «все классы» (см.
`VendorCardScreen.tsx`, блок `isAllClasses(p, s.segment_count) ? <Badge>все
классы</Badge> : ...`). Симптом C2 снят как частный случай общего правила,
а не отдельной веткой по числу сегментов.

### Проверки

- `just ci` — зелёный:
  - backend: 159 passed (новый db-тест контракта `segment_count`)
  - frontend: 91 passed (vitest экраны + helpers + где-разрешён)
  - ruff/mypy/tsc/prettier/eslint чисто
- **API test:** `test_where_allowed_segment_count`
  (`backend/tests/api/test_vendors.py`) — payload contains `segment_count`
  (фикс от Task 1).
- **Frontend tests** (все в `frontend/src/screens/vendors/model.test.ts`,
  один `describe("isAllClasses / standardAllClasses")`, без отдельных файлов):
  - `isAllClasses` — 5 кейсов (полное покрытие, покрытие+excluded, частичное,
    одноклассовый тип, `segment_count=0`).
  - `standardAllClasses` — 2 кейса (все позиции all-classes / хотя бы одна нет).
  - `VendorCardScreen.test.tsx` — блок «Где разрешён»: чип «все классы» вместо
    перечня, сводка в заголовке стандарта, легенда с/без образца-чипа.

## Стекание на PR #21

Ветка работала параллельно с `feat/vendor-card-polish` (PR #21). На момент
исполнения Task 4 PR #21 уже смержена в main (commit `0af62fa`), поэтому
зависимость разрешена. Ветка `feat/where-allowed-polish` стекается на clean main.

## Отложено (E — DS Card modernization)

- **Модернизация DS `Card` + унификация поверхностей (E).** Репозиторный
  `components/ui/card.tsx` — старый shadcn; карточка вендора использует
  локальную `CARD`-константу, матрица/дашборд — DS `Card`. Унификация
  (одного стиля для трёх экранов) — app-wide компромисс, вне объёма одного блока.
  Добавлено в `docs/TECH_DEBT.md`.

## Ключевые решения

### Чистые хелперы + бизнес-логика

Правило «все классы» = `excluded===0 && allowed===segmentCount` — реализовано
как чистые функции в `model.ts` (легко тестировать, не зависит от компонента).
Интеграция в JSX отделена: просто вызываем фукции в render-логике.

### Кастомный триггер вместо форка

Вместо копирования DS `Accordion` целиком, используем `AccordionPrimitive.Trigger`
из radix напрямую и кастомизируем стили через Tailwind класс. Меньше кода,
лучше maintenance.

### Sunken-полосы (инверсия шапок)

Full-bleed `bg-muted` создаёт эффект утопленного контейнера — без отрицательных
отступов, просто убрав горизонтальный паддинг с внешней секции и раздав его
точечно дочерним блокам (см. «Иерархия» выше). Паттерн из дизайна: шапка «Где
разрешён» и шапки per-standard имеют один вид (inverted).

## Ловушки и уроки

### Denominator живость

`segment_count` зависит от текущего состояния таблицы `segment`. Это не view и
не SQL-функция, а обычный `SELECT ... GROUP BY` в роутере на каждый запрос —
ничего не материализовано, при удалении сегмента счётчик пересчитается на
следующем же вызове. Контракт: фронт читает актуальный `segment_count` с
сервера, не кэширует.

### Тонкий кейс: покрытие + исключения = «все классы»?

Сценарий: 5 классов, покрыто 4, исключено 1. Правило требует `excluded===0`,
поэтому это НЕ «все классы». Тест проверяет: `excluded > 0 → false`. Отложенная
разработка: может ли заказчик потребовать «покрытие всех остальных»?

### Легенда sans-border

Легенда — обычный `<p className="mt-3 px-5 text-caption text-muted-foreground">`,
без `border-t` и вообще без рамки/сепаратора — только отступ `mt-3` от дерева
выше. Текст мелкий и серый (`text-caption text-muted-foreground`). Чистая
информация, не набирает внимание.
