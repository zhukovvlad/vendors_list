# Matrix Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пересобрать визуальный слой экрана матрицы «Каталог стандартов» в языке `ReviewItemsTable` (sunken-шапка, липкая колонка «Позиция», чип-язык ячеек, строки-разделы), сохранив pivot-механику. Никакого backend/миграций/маршрутов/инлайн-правки.

**Architecture:** Стиль поверх существующего TanStack Table — не переписываем pivot. Правки в трёх фронтовых точках: `Badge variant="requirement"` (перекрас), `renderCell`/`positionCol` в `columns.tsx` (чипы + двухстрочная позиция + sticky/border-мета), `MatrixScreen.tsx` (прокидка `meta`, sunken-шапка, sticky-left, двухъячеечные строки-разделы, шапка экрана). Плюс `splitQualifier` поднимается в `lib/qualifier.ts`.

**Tech Stack:** React + TS, Vite, TanStack Table/Router/Query, Tailwind v4 (semantic shadcn-токены), shadcn/ui, vitest + MSW.

## Global Constraints

- **БД — источник истины; вычислимое не дублировать в коде** (золотое правило #1/#2). Этот срез БД не трогает вовсе.
- **`components/ui/` — только shadcn-примитивы.** Чипы матрицы — экранные утилитарные классы в `columns.tsx`, НЕ новые DS-компоненты.
- **В `main` не коммитить напрямую.** Работа в ветке `feat/matrix-restyle` (уже создана, 3 коммита спеки). PR в `main`.
- **Перед пушем — полный `just ci`** (не ручной набор npm-скриптов; он недокомплектен относительно CI, напр. без `prettier --check`).
- **`schema.d.ts` — gitignored**, не коммитить; регенерируется `just types`/CI.
- **Токены — наши semantic:** соглашение = `chart-2` (mint, тема-корректный), требование = `warning` (tan), нейтрали = `muted`/`border-strong`. Обе темы бесплатно.
- **Read-only срез.** Никакого `fieldset`-гейта/инлайн-правки. Sticky-top вне среза (только sticky-left).
- **Не ломать контракт `MatrixScreen.test.tsx`:** тексты «Насосы»/«Grundfos»/«Россия»/«Бизнес»/«Эконом»/«Оборудование / ОВиК», aria-label «действующее соглашение», клик по вендору → `/vendors/5`.

**Спека:** [`docs/superpowers/specs/2026-07-15-matrix-restyle-design.md`](../specs/2026-07-15-matrix-restyle-design.md)
**Мокап:** [`docs/superpowers/specs/2026-07-15-matrix-restyle-mockup.html`](../specs/2026-07-15-matrix-restyle-mockup.html)

---

### Task 1: Перекрасить `Badge variant="requirement"` в warning-tan

Изолированная правка одной cva-строки. Текущий тон — `bg-muted text-muted-foreground italic`; спека требует `--warning`.

**Files:**
- Modify: `frontend/src/components/ui/badge-variants.ts:12`

**Interfaces:**
- Consumes: —
- Produces: `Badge variant="requirement"` рендерит warning-tan бейдж (потребитель — `renderCell` в Task 3).

- [ ] **Step 1: Заменить строку варианта `requirement`**

В [badge-variants.ts:12](../../../frontend/src/components/ui/badge-variants.ts#L12) заменить:

```ts
        requirement: "border-transparent bg-muted text-muted-foreground italic",
```

на:

```ts
        requirement: "border-warning/30 bg-warning/10 text-warning",
```

- [ ] **Step 2: Прогнать существующие фронт-тесты (контракт не должен сломаться)**

Run: `cd frontend && npx vitest run src/screens/matrix`
Expected: PASS — тест «рисует групповые шапки…» находит `getByText("Россия")` (перекрас меняет только цвет, не текст).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/badge-variants.ts
git commit -m "feat(ui): requirement-бейдж перекрашен в warning-tan (был muted-italic)"
```

---

### Task 2: Поднять `splitQualifier` в `lib/qualifier.ts` + перенести тест

Второй потребитель (матрица) появляется — выносим чистый хелпер в общий модуль, `vendors/model.ts` оставляет ре-экспорт (импорты вендор-экранов не трогаем).

**Files:**
- Create: `frontend/src/lib/qualifier.ts`
- Create: `frontend/src/lib/qualifier.test.ts`
- Modify: `frontend/src/screens/vendors/model.ts:119-135` (удалить функцию → ре-экспорт)
- Modify: `frontend/src/screens/vendors/model.test.ts:15` (убрать из импорта) и `:148-167` (удалить describe-блок)

**Interfaces:**
- Consumes: —
- Produces: `splitQualifier(name: string): { head: string; qualifier: string | null }` из `@/lib/qualifier` (потребители — Task 4 `positionCol`, а также существующие `PositionRow.tsx`/`WhereAllowedSection.tsx` через ре-экспорт).

- [ ] **Step 1: Создать `lib/qualifier.ts` (перенос функции 1-в-1 с докстрингом)**

```ts
/**
 * Делит имя позиции на «голову» и уточнение в скобках для презентации (первая
 * открывающая скобка). «Насосы (EC двигатель)» → {head:"Насосы", qualifier:"EC двигатель"}.
 * Нет скобки → qualifier=null. Презентационно, НЕ парсер данных.
 */
export function splitQualifier(name: string): {
  head: string
  qualifier: string | null
} {
  const i = name.indexOf("(")
  if (i === -1) return { head: name.trim(), qualifier: null }
  const head = name.slice(0, i).trim()
  const rest = name.slice(i + 1)
  const close = rest.lastIndexOf(")")
  const qualifier = (close === -1 ? rest : rest.slice(0, close)).trim()
  return { head: head || name.trim(), qualifier: qualifier || null }
}
```

- [ ] **Step 2: Создать `lib/qualifier.test.ts` (перенос трёх кейсов)**

```ts
import { describe, expect, it } from "vitest"

import { splitQualifier } from "./qualifier"

describe("splitQualifier", () => {
  it("без скобки → qualifier null", () => {
    expect(splitQualifier("Радиаторы")).toEqual({
      head: "Радиаторы",
      qualifier: null,
    })
  })
  it("со скобкой → голова и уточнение", () => {
    expect(splitQualifier("Насосы (EC двигатель)")).toEqual({
      head: "Насосы",
      qualifier: "EC двигатель",
    })
  })
  it("несбалансированная скобка → всё после '(' как уточнение", () => {
    expect(splitQualifier("Клапаны (Ду50")).toEqual({
      head: "Клапаны",
      qualifier: "Ду50",
    })
  })
})
```

- [ ] **Step 3: Запустить новый тест — должен пройти**

Run: `cd frontend && npx vitest run src/lib/qualifier.test.ts`
Expected: PASS (3 теста).

- [ ] **Step 4: В `vendors/model.ts` заменить функцию на ре-экспорт**

В [model.ts:119-135](../../../frontend/src/screens/vendors/model.ts#L119-L135) удалить весь блок докстринга + функции `splitQualifier` и вставить вместо него:

```ts
// splitQualifier поднят в общий модуль (второй потребитель — матрица).
// Ре-экспорт сохраняет импорты вендор-экранов (`from "./model"`).
export { splitQualifier } from "@/lib/qualifier"
```

- [ ] **Step 5: В `vendors/model.test.ts` убрать дубль**

Убрать `splitQualifier,` из импорт-блока (строка 15) и удалить `describe("splitQualifier", …)` целиком (строки 148-167).

- [ ] **Step 6: Прогнать вендор-тесты и typecheck (ре-экспорт не сломал потребителей)**

Run: `cd frontend && npx vitest run src/screens/vendors && npx tsc -b --noEmit`
Expected: PASS; tsc без ошибок (`PositionRow.tsx`/`WhereAllowedSection.tsx` продолжают импортировать `splitQualifier` из `./model`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/qualifier.ts frontend/src/lib/qualifier.test.ts frontend/src/screens/vendors/model.ts frontend/src/screens/vendors/model.test.ts
git commit -m "refactor(fe): splitQualifier → lib/qualifier + ре-экспорт (второй потребитель — матрица)"
```

---

### Task 3: Чип-язык ячеек в `renderCell`

Заменить `Badge variant="outline"` на чип-язык: вендор-чип, соглашение (mint + ★), Ujin-приписка, требование (warning-бейдж из Task 1), тихий прочерк. Приоритет веток (вендоры → `spec_text` → `—`) сохраняем — это инвариант БД.

**Files:**
- Modify: `frontend/src/screens/matrix/columns.tsx:12-48` (функция `renderCell` + импорты)
- Test: `frontend/src/screens/matrix/columns.test.tsx` (Create)

**Interfaces:**
- Consumes: `Badge variant="requirement"` (Task 1); `MatrixCell` из `./model`.
- Produces: `renderCell(cell: MatrixCell | null): JSX.Element` — рендерит чипы; звезда несёт `aria-label="действующее соглашение"`; вендоры остаются `<Link>` на `/vendors/$vendorId`.

- [ ] **Step 1: Написать падающий тест на `renderCell`**

Create `frontend/src/screens/matrix/columns.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { renderCell } from "./columns"
import type { MatrixCell } from "./model"

const cell = (over: Partial<MatrixCell>): MatrixCell => ({
  segment_id: 11,
  vendors: [],
  spec_text: null,
  note: null,
  ...over,
})

describe("renderCell", () => {
  it("пустая ячейка → тире", () => {
    render(<>{renderCell(null)}</>)
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("требование → текст spec_text", () => {
    render(<>{renderCell(cell({ spec_text: "Россия" }))}</>)
    expect(screen.getByText("Россия")).toBeInTheDocument()
  })
})
```

> Примечание: юнит-тест покрывает только не-ссылочные ветки (`—`, требование) — им не нужен роутер-контекст. Чип-вендор с `<Link>` (клик → `/vendors/5`, aria-label звезды) покрыт интеграционным `MatrixScreen.test.tsx`.

- [ ] **Step 2: Запустить — упадёт (файла columns.test.tsx ещё не собран под новый renderCell / или зелёный на текущем)**

Run: `cd frontend && npx vitest run src/screens/matrix/columns.test.tsx`
Expected: FAIL или PASS на текущем `renderCell` (тире сейчас `text-muted-foreground` — тест на текст «—» пройдёт уже сейчас). Это нормально: тест фиксирует контракт, который мы сохраняем при рестайле. Если PASS — переходим к Step 3 (рестайл не должен его сломать).

- [ ] **Step 3: Переписать `renderCell` на чип-язык**

В [columns.tsx](../../../frontend/src/screens/matrix/columns.tsx) добавить импорт `cn` и переписать `renderCell` (строки 12-48):

```tsx
import { cn } from "@/lib/utils"
```

```tsx
export function renderCell(cell: MatrixCell | null) {
  if (!cell) return <span className="text-muted-foreground/60">—</span>
  if (cell.vendors.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {cell.vendors.map((v) => (
          <Link
            key={v.vendor_id}
            to="/vendors/$vendorId"
            params={{ vendorId: String(v.vendor_id) }}
            className="rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span
              title={v.note ?? undefined}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-caption whitespace-nowrap transition-colors",
                v.starred
                  ? "border-chart-2/40 bg-chart-2/10 text-foreground hover:border-chart-2/60"
                  : "border-border-strong bg-card text-foreground hover:bg-accent"
              )}
            >
              {v.starred && (
                <Star
                  className="size-3 fill-current text-chart-2"
                  aria-label="действующее соглашение"
                />
              )}
              {v.name}
              {v.ujin_integration && (
                <span className="ml-0.5 border-l border-border-strong pl-1 text-[10px] tracking-wide text-muted-foreground">
                  Ujin
                </span>
              )}
            </span>
          </Link>
        ))}
      </div>
    )
  }
  if (cell.spec_text)
    return <Badge variant="requirement">{cell.spec_text}</Badge>
  return <span className="text-muted-foreground/60">—</span>
}
```

- [ ] **Step 4: Прогнать юнит и интеграционный тесты матрицы**

Run: `cd frontend && npx vitest run src/screens/matrix`
Expected: PASS — `columns.test.tsx` (тире/требование) и `MatrixScreen.test.tsx` (звезда aria-label, «Grundfos», клик → `/vendors/5`).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/matrix/columns.tsx frontend/src/screens/matrix/columns.test.tsx
git commit -m "feat(matrix): чип-язык ячеек (соглашение=mint/★, Ujin-приписка, тихий прочерк)"
```

---

### Task 4: Двухстрочная колонка «Позиция» + sticky/border-мета + augmentation

Колонка «Позиция» рендерит голову/уточнение двумя строками; колонки получают `meta.className`/`meta.headerClassName` для sticky-left (позиция) и вертикальных разделителей групп. Плюс module augmentation `ColumnMeta` (иначе tsc падает).

**Files:**
- Modify: `frontend/src/screens/matrix/model.ts` (augmentation)
- Modify: `frontend/src/screens/matrix/columns.tsx:50-83` (`positionCol` + `buildColumnDefs`)

**Interfaces:**
- Consumes: `splitQualifier` из `@/lib/qualifier` (Task 2).
- Produces: колоночные дефы с `meta.className` (тело) и `meta.headerClassName` (шапка); типы `ColumnMeta.className?: string` / `headerClassName?: string` — потребитель Task 5 (прокидка в `TableHead`/`TableCell`).

- [ ] **Step 1: Добавить module augmentation в `matrix/model.ts`**

В конец [model.ts](../../../frontend/src/screens/matrix/model.ts) добавить (импорт типа `RowData` — вверх файла):

```ts
import type { RowData } from "@tanstack/react-table"
```

```ts
// Разрешаем per-column CSS-классы через meta (sticky-колонка, разделители групп).
// TanStack не типизирует meta по умолчанию — расширяем интерфейс.
declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    className?: string
    headerClassName?: string
  }
}
```

- [ ] **Step 2: Переписать `positionCol` (двухстрочная позиция + sticky-мета)**

В [columns.tsx](../../../frontend/src/screens/matrix/columns.tsx) добавить импорт `splitQualifier` и переписать `positionCol` (строки 55-61):

```tsx
import { splitQualifier } from "@/lib/qualifier"
```

```tsx
  const positionCol = ch.display({
    id: "position",
    header: "Позиция",
    cell: ({ row }) => {
      const { head, qualifier } = splitQualifier(row.original.position_name)
      return (
        <span className="font-medium leading-tight">
          {head}
          {qualifier && (
            <span className="block text-caption font-normal text-muted-foreground">
              {qualifier}
            </span>
          )}
        </span>
      )
    },
    meta: {
      // group-hover: подсветка липкой ячейки вместе со строкой (её opaque bg-card
      // маскирует hover:bg-muted/50 строки — нужен собственный group-hover).
      className:
        "sticky left-0 z-[2] min-w-[220px] bg-card border-r border-border group-hover:bg-muted/50",
      headerClassName: "sticky left-0 z-[4] bg-muted border-r border-border",
    },
  }) as ColumnDef<MatrixRow, unknown>
```

- [ ] **Step 3: Вертикальные разделители групп в `buildColumnDefs`**

Заменить блок `segCols` (строки 63-80) так, чтобы первый лист каждой группы и заголовок группы несли левый бордер:

```tsx
  const segCols = columns.flatMap((grp, gi) => {
    // Левый разделитель — МЕЖДУ группами; у первой группы не рисуем, иначе двойная
    // линия вплотную к border-r липкой «Позиции».
    const border = gi > 0 ? "border-l border-border" : undefined
    const leaves = grp.segments.map(
      (s, idx) =>
        ch.display({
          id: String(s.id),
          header: s.name,
          cell: ({ row }) => renderCell(cellFor(row.original, s.id)),
          meta:
            idx === 0 && border
              ? { className: border, headerClassName: border }
              : undefined,
        }) as ColumnDef<MatrixRow, unknown>
    )
    if (!grp.group) return leaves
    return [
      ch.group({
        id: `g${grp.group.id}`,
        header: grp.group.name,
        columns: leaves,
        meta: { headerClassName: cn(border, "text-center") },
      }) as ColumnDef<MatrixRow, unknown>,
    ]
  })
```

> `cn` уже импортирован в `columns.tsx` (Task 3 Step 3). `cn(undefined, "text-center")` → `"text-center"`.

- [ ] **Step 4: Typecheck (augmentation работает, meta типизирован)**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: без ошибок (без augmentation здесь была бы ошибка «`meta` unknown property»).

- [ ] **Step 5: Прогнать тесты матрицы (структура строк/колонок не поехала)**

Run: `cd frontend && npx vitest run src/screens/matrix`
Expected: PASS — `findByText("Насосы")` работает (у MSW-позиции нет скобки → `head="Насосы"`), шапки «Бизнес»/«Эконом» на месте.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/matrix/model.ts frontend/src/screens/matrix/columns.tsx
git commit -m "feat(matrix): двухстрочная позиция + sticky/border-мета колонок (+ColumnMeta augmentation)"
```

---

### Task 5: `MatrixScreen` — прокидка меты, sunken-шапка, sticky-left, строки-разделы, шапка экрана

Финальная сборка: `TableHead`/`TableCell` читают `meta`; шапка sunken + uppercase; строки-разделы в две ячейки (sticky-left подпись + пустой добор); лёгкая шапка экрана над фильтрами.

**Files:**
- Modify: `frontend/src/screens/matrix/MatrixScreen.tsx` (импорт `cn`; шапка экрана; `TableHeader`/`TableHead`/`TableCell`; строки-разделы)

**Interfaces:**
- Consumes: `meta.className`/`meta.headerClassName` из колоночных дефов (Task 4); `leafCount` (уже есть).
- Produces: финальный рестайл-экран (read-only).

- [ ] **Step 1: Добавить импорт `cn`**

В [MatrixScreen.tsx](../../../frontend/src/screens/matrix/MatrixScreen.tsx) в блок импортов добавить:

```tsx
import { cn } from "@/lib/utils"
```

- [ ] **Step 2: Лёгкая шапка экрана над фильтр-`Card`**

Сразу после открывающего `<div className="flex flex-col gap-4 p-6 text-foreground">` (строка 97) вставить первым потомком:

```tsx
      <div>
        <h1 className="text-h3 font-semibold tracking-tight">
          Каталог стандартов
        </h1>
        <p className="text-small text-muted-foreground">
          Какие вендоры допущены в каком классе объекта.
        </p>
      </div>
```

- [ ] **Step 3: Sunken + uppercase шапка; прокидка `headerClassName`**

Заменить `<TableHeader>` (строка 165) на:

```tsx
        <TableHeader className="bg-muted [&_th]:uppercase">
```

И в рендере заголовков (строки 168-174) прокинуть класс — заменить `<TableHead key={h.id} colSpan={h.colSpan}>` на:

```tsx
                <TableHead
                  key={h.id}
                  colSpan={h.colSpan}
                  className={cn(h.column.columnDef.meta?.headerClassName)}
                >
```

- [ ] **Step 4: Строки-разделы в две ячейки (sticky-left подпись + добор)**

Заменить ветку `dr.kind === "section"` (строки 180-188) на:

```tsx
            dr.kind === "section" ? (
              <TableRow key={dr.key} className="bg-muted hover:bg-muted">
                <TableCell className="sticky left-0 z-[1] border-r border-border bg-muted text-caption font-medium uppercase tracking-wide text-muted-foreground">
                  {dr.categoryPath}
                </TableCell>
                <TableCell colSpan={leafCount - 1} className="bg-muted" />
              </TableRow>
            ) : (
```

- [ ] **Step 5: Прокидка `meta.className` в ячейки тела + `group` на строку**

В рендере строк-позиций (не-section ветка, строка ~190) заменить `<TableRow key={dr.key}>` на (`group` включает `group-hover:` липкой ячейки из Task 4):

```tsx
              <TableRow key={dr.key} className="group">
```

В рендере ячеек позиции (строки 194-198) заменить `<TableCell key={c.id}>` на:

```tsx
                    <TableCell
                      key={c.id}
                      className={cn(c.column.columnDef.meta?.className)}
                    >
```

- [ ] **Step 6: Плотность ячеек**

Дать таблице более плотный вертикальный ритм — заменить `<Table>` (строка 164) на:

```tsx
      <Table className="[&_td]:py-1.5">
```

> `tabular-nums` из спеки — **не применимо**: в ячейках имена вендоров/текст требований, числовых колонок нет. Записано осознанно, а не пропущено.

- [ ] **Step 7: Прогнать интеграционный тест матрицы**

Run: `cd frontend && npx vitest run src/screens/matrix/MatrixScreen.test.tsx`
Expected: PASS — все 4 кейса (шапки/звезда/требование/раздел; дебаунс-поиск; пагинация; клик по вендору). CSS-uppercase не меняет `textContent`, `getByText` устойчив.

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/screens/matrix/MatrixScreen.tsx
git commit -m "feat(matrix): sunken-шапка, sticky-left «Позиция», плотность, двухъячеечные разделы, шапка экрана"
```

---

### Task 6: Полный `just ci`, devlog, PR

**Files:**
- Create: `docs/devlog/2026-07-15-matrix-restyle.md`

**Interfaces:**
- Consumes: результат Tasks 1-5.
- Produces: зелёный `just ci`, devlog, PR в `main`.

- [ ] **Step 1: Полный `just ci` (полный контур: prettier/eslint/tsc/vitest фронта + backend-часть без изменений)**

Run: `just ci`
Expected: всё зелёное. Если `prettier --check` ругается — `cd frontend && npx prettier --write src/screens/matrix src/lib/qualifier.ts src/components/ui/badge-variants.ts` и переприкоммитить.

- [ ] **Step 2: Ручная визуальная проверка (обе темы)**

Run: `just dev-front` (+ `just dev-back` при необходимости данных)
Проверить `/matrix`: sunken-шапка с группами, липкая колонка «Позиция» при горизонтальном скролле, mint-чипы соглашений со ★, warning-бейдж требования, Ujin-приписка, строки-разделы залипают слева, тумблер темы — обе темы читаемы. Прокрутить горизонтально: «Позиция» и подписи разделов остаются на месте (sticky-top НЕ ожидаем — вне среза).

- [ ] **Step 3: Написать devlog**

Create `docs/devlog/2026-07-15-matrix-restyle.md`: что сделано (рестайл матрицы в языке ReviewItemsTable), решения (стиль поверх pivot; sticky-left без sticky-top; чипы экранные; `splitQualifier`→`lib/`; requirement→warning; ColumnMeta augmentation), находки ревью спеки (sticky-top инертен под overflow-x; vendors/spec_text — инвариант БД), ссылки на спек/мокап/PR.

- [ ] **Step 4: Commit devlog + push + PR**

```bash
git add docs/devlog/2026-07-15-matrix-restyle.md
git commit -m "docs(devlog): рестайл матрицы «Каталог стандартов»"
git push -u origin feat/matrix-restyle
gh pr create --base main --title "feat(matrix): рестайл «Каталог стандартов» в языке ReviewItemsTable" --body "См. spec/2026-07-15-matrix-restyle-design.md. Визуальный рестайл матрицы: sunken-шапка, sticky-left «Позиция», чип-язык, строки-разделы. Без backend/миграций/маршрутов/инлайн-правки.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 5: Дождаться зелёного CI на PR**

Run: `gh pr checks --watch`
Expected: все проверки зелёные.

---

## Self-Review

**Spec coverage:**
- Sunken-шапка → Task 5 (Step 3). ✅
- Sticky-left «Позиция» → Task 4 (meta) + Task 5 (прокидка). ✅
- Чип-язык (mint-соглашение/★/Ujin/требование/тире) → Task 1 (requirement) + Task 3. ✅
- Строки-разделы две ячейки → Task 5 (Step 4). ✅
- Двухстрочная позиция (`splitQualifier`) → Task 2 + Task 4. ✅
- Шапка экрана → Task 5 (Step 2). ✅
- Плотность (паддинги + hover строки/липкой ячейки) → Task 4 (group-hover меты) + Task 5 (Step 5 `group`, Step 6 `[&_td]:py-1.5`). ✅ `tabular-nums` — не применимо (нет числовых колонок), записано явно.
- Обе темы через токены → chart-2/warning/muted (Tasks 1,3,4,5). ✅
- ColumnMeta augmentation → Task 4 (Step 1). ✅
- `splitQualifier` в `lib/` + ре-экспорт → Task 2. ✅
- requirement→warning → Task 1. ✅
- Вне среза (sticky-top, инлайн-правка, backend) — нигде не реализуется. ✅

**Placeholder scan:** плейсхолдеров нет. Тест-хелпер Task 3 Step 1 минимален (без роутер-контекста для не-ссылочных веток).

**Type consistency:** `splitQualifier` сигнатура едина (Task 2 ↔ Task 4). `meta.className`/`headerClassName` объявлены в Task 4 Step 1 и потребляются под теми же именами в Task 4 (дефы) и Task 5 (прокидка). `renderCell(cell: MatrixCell | null)` — сигнатура не менялась.
