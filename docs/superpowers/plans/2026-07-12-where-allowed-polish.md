# Полиш блока «Где разрешён» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести блок «Где разрешён» на карточке вендора до утверждённого дизайна: иерархия уровней (утопленная полоса-заголовок с leading-шевроном, направляющая, тонкие разделители), правило «все классы» (свёртка полного покрытия в один тихий чип) и тихая легенда.

**Architecture:** Бэкенд отдаёт знаменатель (`segment_count` — всего классов у типа) одним агрегатом; SQL-функция правила не меняется. Правило «все классы» — чистые презентационные хелперы во фронте. Вёрстка блока переработана в `VendorCardScreen.tsx`: кастомный триггер на `AccordionPrimitive.Trigger` (Radix напрямую) с leading-шевроном — штатный `components/ui/accordion.tsx` НЕ форкаем.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy Core (async), PostgreSQL; Vite + React + TS, shadcn/ui + Tailwind (токены), TanStack Router/Query, radix-ui, vitest + MSW.

Спека: [docs/superpowers/specs/2026-07-12-where-allowed-polish-design.md](../specs/2026-07-12-where-allowed-polish-design.md).

## Global Constraints

Каждая задача неявно наследует (CLAUDE.md «Золотые правила» + решения спеки):

- **Schema-first, без ORM.** Только SQLAlchemy Core (`text(...)`), bind-параметры.
- **Читающий эндпоинт** — `Depends(require_user)` + `Depends(read_conn)`; правило «все классы» — презентационный роллап, в БД НЕ переносится (golden-rule #6). SQL-функцию `vendor_where_allowed` НЕ трогаем, **миграций БД нет**.
- **Только семантические токены DS. Новых токенов НЕ заводить.** Акцент → `text-primary`; серый ramp → `text-muted-foreground`/`text-foreground`; sunken-полоса → `bg-muted`; делители → `border-border`, тончайшие → `border-border/60` (альфа-модификатор существующего токена); пунктир excluded → `border-border-strong border-dashed`; фокус → `--ring`.
- **DS `components/ui/accordion.tsx` НЕ форкаем.** Leading-шеврон — кастомный триггер на `AccordionPrimitive.Trigger`/`AccordionPrimitive.Header` из пакета `radix-ui` (тот же импорт, что в самом accordion.tsx), состояние через `group-data-[state=open]`.
- **Поверхности не трогаем.** Секции остаются `<section className={CARD}>`; перевод на DS `<Card>` — отдельный follow-up (Task 4 заносит в TECH_DEBT).
- **UI только на русском.**
- **Типы сквозные:** после правки бэкенд-контракта — `just types` (регенерит `frontend/src/api/schema.d.ts`, gitignored, не коммитим).
- **Фронт-задачи:** `npm run format` + `npm run format:check` ПЕРЕД коммитом (не только vitest/typecheck).
- **`main` зелёный:** ветка `feat/where-allowed-polish` **стекается на `feat/vendor-card-polish` (PR #21, открыт)** — мерж после #21; `just ci` зелёный перед PR, мерж через PR.
- **db-тесты (маркер `db`)** идут на тест-ветке Neon; `DATABASE_URL_TEST` присутствует локально.

---

## Файловая структура

**Изменить:**
- `backend/app/schemas/__init__.py` — поле `segment_count: int` в `WhereAllowedStandard`.
- `backend/app/routers/vendors.py` — агрегат `segment_count` в `get_where_allowed`.
- `backend/tests/api/test_vendors.py` — api-тест на `segment_count`.
- `frontend/src/screens/vendors/model.ts` — хелперы `isAllClasses`, `standardAllClasses`.
- `frontend/src/screens/vendors/model.test.ts` — юниты правила (5 кейсов).
- `frontend/src/screens/vendors/VendorCardScreen.tsx` — рерайт блока «Где разрешён».
- `frontend/src/screens/vendors/VendorCardScreen.test.tsx` — смоук редизайна.
- `frontend/src/test/msw/handlers.ts` — `segment_count` в `whereAllowedFixture`.
- `CLAUDE.md`, `docs/TECH_DEBT.md`, `docs/devlog/2026-07-12-where-allowed-polish.md` (Task 4).

---

## Task 1: Бэкенд — `segment_count` в контракте where-allowed

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/vendors.py`
- Test: `backend/tests/api/test_vendors.py`

**Interfaces:**
- Consumes: фабрики `make_building_type`/`make_segment`/`make_category`/`make_position`/`make_vendor`/`make_listing` ([backend/tests/factories.py](../../backend/tests/factories.py)); фикстуры `client`/`as_viewer`/`db_conn`; `WhereAllowedStandard`/`WhereAllowed`, `text`, `read_conn`/`require_user` (уже в `vendors.py`).
- Produces: `WhereAllowedStandard.segment_count: int` (всего классов у `building_type`) в ответе `GET /vendors/{id}/where-allowed`.

- [ ] **Step 1: Написать падающий api-тест**

В конец `backend/tests/api/test_vendors.py` (файл уже импортирует `f` и `text`):

```python
async def test_where_allowed_segment_count(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="wa-segcount")
    s1 = await f.make_segment(db_conn, building_type_id=bt, name="Кл-1", sort_order=1)
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-2", sort_order=2)
    await f.make_segment(db_conn, building_type_id=bt, name="Кл-3", sort_order=3)
    cat = await f.make_category(db_conn, name="wa-sc-cat")
    pos = await f.make_position(db_conn, category_id=cat, name="wa-sc-pos")
    v = await f.make_vendor(db_conn, name="wa-sc-v")
    await f.make_listing(
        db_conn, position_id=pos, segment_id=s1, vendor_id=v, status="allowed"
    )

    resp = await client.get(f"/vendors/{v}/where-allowed")
    assert resp.status_code == 200
    std = next(s for s in resp.json()["standards"] if s["building_type_id"] == bt)
    assert std["segment_count"] == 3  # знаменатель = ВСЕ сегменты типа
    assert len(std["positions"][0]["chips"]) == 1  # вендор только в одном
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -k segment_count -v`
Expected: FAIL (`KeyError: 'segment_count'` — поля в ответе нет).

- [ ] **Step 3: Добавить поле в схему**

В `backend/app/schemas/__init__.py`, класс `WhereAllowedStandard` — добавить поле (после `position_count`):

```python
class WhereAllowedStandard(BaseModel):
    building_type_id: int
    building_type_name: str
    position_count: int
    segment_count: int      # всего классов (сегментов) у типа — знаменатель «все классы»
    positions: list[WhereAllowedPosition]
```

- [ ] **Step 4: Проставить `segment_count` в эндпоинте**

В `backend/app/routers/vendors.py`, функция `get_where_allowed`. При конструировании `WhereAllowedStandard` добавить `segment_count=0`, а перед `return` — заполнить одним агрегатом (таблица `segment` крошечная — группируем целиком, без фильтра, чтобы не биндить массив):

Изменить конструктор (в цикле группировки):

```python
            standards.append(
                WhereAllowedStandard(
                    building_type_id=r["building_type_id"],
                    building_type_name=r["building_type_name"],
                    position_count=0,
                    segment_count=0,
                    positions=[],
                )
            )
```

Заменить хвост `return WhereAllowed(standards=standards)` на:

```python
    if standards:
        counts = {
            row["building_type_id"]: row["n"]
            for row in (
                await conn.execute(
                    text(
                        "SELECT building_type_id, count(*) AS n "
                        "FROM segment GROUP BY building_type_id"
                    )
                )
            ).mappings()
        }
        for s in standards:
            s.segment_count = counts.get(s.building_type_id, 0)

    return WhereAllowed(standards=standards)
```

> `segment` не имеет soft-delete/флага активности (DDL 0001:56–66) — `count(*)` без фильтра корректен.

- [ ] **Step 5: Прогнать — PASS + типы**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -v` — Expected: PASS (старые where-allowed тесты + новый `segment_count`).
Run: `just types` — Expected: `schema.d.ts` содержит `segment_count` в `WhereAllowedStandard`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/tests/api/test_vendors.py
git commit -m "feat(api): segment_count в where-allowed (знаменатель правила «все классы»)"
```

> `schema.d.ts` gitignored — не стейджим.

---

## Task 2: Фронт — правило «все классы» (чистые хелперы)

**Files:**
- Modify: `frontend/src/screens/vendors/model.ts`
- Modify: `frontend/src/screens/vendors/model.test.ts`

**Interfaces:**
- Produces: `isAllClasses(position, segmentCount) -> boolean`, `standardAllClasses(standard) -> boolean`. Используются в Task 3.

- [ ] **Step 1: Написать падающие юниты**

В `frontend/src/screens/vendors/model.test.ts` добавить импорт `isAllClasses, standardAllClasses` к существующему импорту из `./model` и блок:

```ts
describe("isAllClasses / standardAllClasses", () => {
  const pos = (states: string[]) => ({
    chips: states.map((state, i) => ({ segment_id: i, state })),
  })

  it("полное покрытие без excluded → все классы", () => {
    expect(isAllClasses(pos(["allowed", "allowed"]), 2)).toBe(true)
  })
  it("полное покрытие, но есть excluded → НЕ все классы (перечень)", () => {
    expect(isAllClasses(pos(["allowed", "allowed", "excluded"]), 3)).toBe(false)
  })
  it("частичное покрытие → НЕ все классы", () => {
    expect(isAllClasses(pos(["allowed", "allowed"]), 4)).toBe(false)
  })
  it("одноклассовый тип с покрытием → все классы", () => {
    expect(isAllClasses(pos(["allowed"]), 1)).toBe(true)
  })
  it("segment_count 0 → не все классы (страховка)", () => {
    expect(isAllClasses(pos([]), 0)).toBe(false)
  })

  it("стандарт: все позиции all-classes → true", () => {
    const std = {
      segment_count: 2,
      positions: [pos(["allowed", "allowed"]), pos(["allowed", "allowed"])],
    }
    expect(standardAllClasses(std)).toBe(true)
  })
  it("стандарт: хотя бы одна позиция не all-classes → false", () => {
    const std = {
      segment_count: 2,
      positions: [pos(["allowed", "allowed"]), pos(["allowed"])],
    }
    expect(standardAllClasses(std)).toBe(false)
  })
})
```

Run: `cd frontend; npm run test -- model.test` — Expected: FAIL (хелперов нет).

- [ ] **Step 2: Реализовать хелперы**

В `frontend/src/screens/vendors/model.ts` добавить (типы структурные — не тянем schema.d.ts):

```ts
type ChipState = { state: string }
type CoveragePosition = { chips: ChipState[] }
type CoverageStandard = { segment_count: number; positions: CoveragePosition[] }

/**
 * Позиция покрыта «все классы»: вендор разрешён во ВСЕХ сегментах типа и нет
 * исключённых. `excluded > 0` всегда даёт false — исключение не прячется за сводкой.
 */
export function isAllClasses(
  position: CoveragePosition,
  segmentCount: number
): boolean {
  if (segmentCount <= 0) return false
  let allowed = 0
  let excluded = 0
  for (const c of position.chips) {
    if (c.state === "allowed") allowed++
    else if (c.state === "excluded") excluded++
  }
  return excluded === 0 && allowed === segmentCount
}

/** Стандарт целиком «все классы»: он непустой и все его позиции — «все классы». */
export function standardAllClasses(standard: CoverageStandard): boolean {
  return (
    standard.positions.length > 0 &&
    standard.positions.every((p) => isAllClasses(p, standard.segment_count))
  )
}
```

- [ ] **Step 3: Прогнать — PASS**

Run: `cd frontend; npm run test -- model.test` — Expected: PASS.
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.

- [ ] **Step 4: format + commit**

```bash
cd frontend; npm run format; npm run format:check
```
Expected: clean. Затем:

```bash
git add frontend/src/screens/vendors/model.ts frontend/src/screens/vendors/model.test.ts
git commit -m "feat(vendors): правило «все классы» — хелперы isAllClasses/standardAllClasses"
```

---

## Task 3: Фронт — рерайт блока «Где разрешён» (иерархия, «все классы», легенда, фокус)

**Files:**
- Modify: `frontend/src/test/msw/handlers.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: `isAllClasses`/`standardAllClasses` (Task 2), `segment_count` в payload (Task 1); существующие `pluralStandards`/`pluralPositions`/`excludedTooltip`/`hasExcludedChips`/`whereAllowedLegend`/`WHERE_ALLOWED_EMPTY`; хуки/логика шапки/алиасов/бренда — БЕЗ изменений.
- Produces: переработанный блок «Где разрешён» (полоса-заголовок на Radix-триггере с leading-шевроном, направляющая, чип «все классы», сводка в заголовке, тихая легенда).

- [ ] **Step 1: Добавить `segment_count` в MSW-фикстуру**

В `frontend/src/test/msw/handlers.ts`, объект `whereAllowedFixture` — добавить `segment_count` в standard (у типа 2 класса: Делюкс+Бизнес):

```ts
    {
      building_type_id: 1,
      building_type_name: "Жилой дом",
      position_count: 1,
      segment_count: 2,
      positions: [
```

(остальное без изменений).

- [ ] **Step 2: Написать падающие смоук-тесты**

В `frontend/src/screens/vendors/VendorCardScreen.test.tsx`, в `describe("VendorCardScreen — Где разрешён")` добавить:

```tsx
it("полное покрытие без excluded → чип «все классы» вместо перечня", async () => {
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
                position_name: "Радиаторы отопления",
                chips: [
                  { segment_id: 11, segment_name: "Делюкс", state: "allowed", release_label: null },
                  { segment_id: 12, segment_name: "Эконом", state: "allowed", release_label: null },
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
  await userEvent.click(screen.getByText("Жилой дом"))
  expect(await screen.findByText("все классы")).toBeInTheDocument()
  expect(screen.queryByText("Делюкс")).not.toBeInTheDocument()
})

it("стандарт, где все позиции покрыты → сводка «· все классы» в заголовке", async () => {
  server.use(
    http.get("/api/vendors/:vendorId/where-allowed", () =>
      HttpResponse.json({
        standards: [
          {
            building_type_id: 1,
            building_type_name: "Жилой дом",
            position_count: 1,
            segment_count: 1,
            positions: [
              {
                position_id: 100,
                position_name: "Радиаторы отопления",
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
  expect(await screen.findByText(/1 позиция · все классы/)).toBeInTheDocument()
})

it("легенда без рамки: при excluded — образец-чип и пояснение", async () => {
  renderAt() // дефолтная фикстура содержит excluded «Бизнес»
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  expect(
    await screen.findByText(/был в последнем релизе, исключён/)
  ).toBeInTheDocument()
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (чипа «все классы»/сводки/новой легенды ещё нет; старая вёрстка).

- [ ] **Step 3: Рерайт блока в `VendorCardScreen.tsx`**

1) Импорты: удалить `AccordionTrigger` из импорта `@/components/ui/accordion`, добавить Radix-примитив и иконку, расширить импорт из `./model`:

```tsx
import { Accordion as AccordionPrimitive } from "radix-ui"
import { Award, ChevronRight, Merge, Plus, Star, X } from "lucide-react"
```

```tsx
import {
  Accordion,
  AccordionContent,
  AccordionItem,
} from "@/components/ui/accordion"
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
  standardAllClasses,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"
```

2) Полностью заменить JSX секции `{/* Где разрешён */}` (от `<section className={\`${CARD} px-5 py-[15px]\`}>` до её закрывающего `</section>`) на версию с `py-[15px]` без горизонтального паддинга у секции (полосы-заголовки full-bleed, остальные блоки получают свой `px-5`):

```tsx
      {/* Где разрешён */}
      <section className={`${CARD} py-[15px]`}>
        <div className="flex items-baseline justify-between px-5">
          <span className="text-caption text-muted-foreground uppercase">
            Где разрешён
          </span>
          {standards.length > 0 && (
            <span className="text-caption text-muted-foreground">
              {standards.length} {pluralStandards(standards.length)} ·{" "}
              {positionTotal} {pluralPositions(positionTotal)}
            </span>
          )}
        </div>

        {whereAllowed.isPending ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            Загрузка…
          </div>
        ) : whereAllowed.isError ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            Не удалось загрузить
          </div>
        ) : standards.length === 0 ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            {WHERE_ALLOWED_EMPTY}
          </div>
        ) : (
          <>
            <Accordion type="multiple" className="mt-2.5">
              {standards.map((s) => {
                const count = `${s.position_count} ${pluralPositions(s.position_count)}`
                const summary = standardAllClasses(s)
                  ? `${count} · все классы`
                  : count
                return (
                  <AccordionItem
                    key={s.building_type_id}
                    value={String(s.building_type_id)}
                    className="border-b-0"
                  >
                    <AccordionPrimitive.Header className="flex">
                      <AccordionPrimitive.Trigger className="group flex w-full items-center gap-2.5 border-y border-border bg-muted px-5 py-2.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <ChevronRight
                          aria-hidden
                          className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 group-data-[state=open]:text-primary"
                        />
                        <span className="flex-1 text-small font-medium">
                          {s.building_type_name}
                        </span>
                        <span className="text-caption text-muted-foreground">
                          {summary}
                        </span>
                      </AccordionPrimitive.Trigger>
                    </AccordionPrimitive.Header>
                    <AccordionContent className="mr-5 ml-8 border-l border-border pl-4">
                      <div className="divide-y divide-border/60">
                        {s.positions.map((p) => (
                          <div
                            key={p.position_id}
                            className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-2"
                          >
                            <span className="flex-1 text-small">
                              {p.position_name}
                            </span>
                            {isAllClasses(p, s.segment_count) ? (
                              <Badge
                                variant="outline"
                                className="text-muted-foreground"
                              >
                                все классы
                              </Badge>
                            ) : (
                              <div className="flex w-full flex-wrap gap-1.5">
                                {p.chips.map((c) =>
                                  c.state === "allowed" ? (
                                    <Badge
                                      key={c.segment_id}
                                      variant="outline"
                                      className="bg-accent"
                                    >
                                      {c.segment_name}
                                    </Badge>
                                  ) : (
                                    <Badge
                                      key={c.segment_id}
                                      variant="outline"
                                      className="border-dashed border-border-strong text-muted-foreground line-through"
                                      title={excludedTooltip(c.release_label)}
                                      aria-label={excludedTooltip(c.release_label)}
                                    >
                                      {c.segment_name}
                                    </Badge>
                                  )
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                )
              })}
            </Accordion>
            {hasExcludedChips(standards) ? (
              <p className="mt-3 flex items-center gap-1.5 px-5 text-caption text-muted-foreground">
                <span className="rounded-sm border border-dashed border-border-strong px-1.5 line-through">
                  класс
                </span>
                — был в последнем релизе, исключён · показано текущее состояние
                стандартов
              </p>
            ) : (
              <p className="mt-3 px-5 text-caption text-muted-foreground">
                {whereAllowedLegend(false)}
              </p>
            )}
          </>
        )}
      </section>
```

> Полоса-заголовок — кастомный триггер на `AccordionPrimitive.Trigger` (DS `accordion.tsx` не тронут); leading-шеврон `ChevronRight` поворачивается и красится в `text-primary` по `group-data-[state=open]`. Направляющая — `ml-8 border-l border-border pl-4`; разделители позиций — `divide-y divide-border/60`. Легенда — без рамки-коробки, с мини-образцом зачёркнутого чипа; текст без-excluded берём из существующего `whereAllowedLegend(false)`.

- [ ] **Step 4: Прогнать — PASS + typecheck + format**

Run: `cd frontend; npm run test -- VendorCardScreen model.test` — Expected: PASS (старые сценарии где-разрешён + 3 новых).
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.
Run: `cd frontend; npm run format` затем `npm run format:check` — Expected: чисто.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/test/msw/handlers.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): редизайн блока «Где разрешён» — иерархия, «все классы», тихая легенда"
```

---

## Task 4: Финализация — `just ci`, документация, PR

**Files:**
- Modify: `CLAUDE.md`, `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-12-where-allowed-polish.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли`. Если db-тесты скипаются без `DATABASE_URL_TEST` — ок (прогонятся в CI). Красно — STOP, чинить, не писать доки поверх красного.

- [ ] **Step 2: TECH_DEBT — follow-up модернизации DS Card**

В `docs/TECH_DEBT.md` в раздел карточки вендора добавить пункт:

```markdown
- **Модернизация DS `Card` + унификация поверхностей.** Репозиторный
  `components/ui/card.tsx` — старый вариант shadcn (`p-4`, `shadow-elevation-2`, без
  border-разделения секций, без `CardFooter`/`CardAction`/`--card-spacing`); карточка
  вендора вовсе использует локальную `CARD`-константу (`<section>`), матрица/дашборд —
  DS `Card`. Follow-up: обновить примитив `Card` до актуального shadcn и унифицировать
  поверхности трёх экранов (вид — rounded-lg+elevation vs плоский rounded-xl — решается
  один раз для всех). App-wide, вне полиша одного блока.
```

- [ ] **Step 3: CLAUDE.md**

- Карта репо: в `screens/vendors/` отметить хелперы `isAllClasses`/`standardAllClasses` и переработанный блок «Где разрешён» (кастомный Radix-триггер, правило «все классы»); в роутере `vendors` — `where-allowed` отдаёт `segment_count`.
- §5 (карточка вендора): отметить, что блок «Где разрешён» доведён до утверждённой иерархии + свёртка «все классы».

- [ ] **Step 4: Devlog**

Create `docs/devlog/2026-07-12-where-allowed-polish.md` — хронология: находка нулевого шага (payload без знаменателя → `segment_count` одним агрегатом, SQL-функция не тронута, живость сегментов по DDL); правило «все классы» чистыми хелперами (`excluded===0 && allowed===segment_count`, тонкий кейс «покрытие+excluded → перечень»); кастомный триггер на `AccordionPrimitive.Trigger` вместо форка DS accordion (leading-шеврон по `group-data-[state=open]`); иерархия (sunken-полоса full-bleed, направляющая, `divide-border/60`); тихая легенда с мини-чипом; снятие визуального симптома C2 (корень остаётся); отложенная модернизация DS Card. Отметить стекование ветки на PR #21.

- [ ] **Step 5: Commit + push + PR**

```bash
git add CLAUDE.md docs/TECH_DEBT.md docs/devlog/2026-07-12-where-allowed-polish.md
git commit -m "docs(where-allowed-polish): devlog + CLAUDE.md карта/§5 + TECH_DEBT (модернизация DS Card)"
git push -u origin feat/where-allowed-polish
gh pr create --base main --title "feat: полиш блока «Где разрешён» (иерархия + «все классы»)" --body "..."
```

> Ветка стекается на PR #21: если #21 ещё не влит, отметить в теле PR зависимость (мерж после #21) либо нацелить PR на `feat/vendor-card-polish` — решает контроллер при исполнении.

---

## Self-Review

**Spec coverage:**
- §A контракт (`segment_count`, агрегат, SQL-функция не тронута, `just types`) → Task 1. ✓
- §B правило «все классы» (`allowed==segment_count && excluded==0`, тонкий кейс покрытие+excluded, сводка в заголовке, снятие симптома C2) → Task 2 (хелперы) + Task 3 (интеграция/сводка). ✓
- §C иерархия (sunken-полоса, кастомный Radix-триггер + leading-шеврон, направляющая, `border-border/60`) → Task 3. ✓
- §D легенда без рамки + фокус (`--ring` кольцо на триггере) → Task 3. ✓
- §E поверхности отложены → Task 4 (TECH_DEBT). ✓
- §F тесты (5 кейсов правила → Task 2; смоук «все классы»/сводка/легенда → Task 3; контракт-тест → Task 1) → покрыто. ✓
- §G границы (только блок, шапку/алиасы/бренд не трогаем) → Task 3 меняет только секцию «Где разрешён». ✓

**Placeholder scan:** код полный в каждом шаге; «...» только в `gh pr create --body` (Task 4). TODO/TBD нет.

**Type consistency:** `WhereAllowedStandard.segment_count: int` (Task 1) ↔ фикстуры/хелперы читают `segment_count` (Task 2/3). `isAllClasses(position, segmentCount)` / `standardAllClasses(standard)` — сигнатуры совпадают между Task 2 (определение) и Task 3 (вызовы). `AccordionPrimitive` из `radix-ui` — тот же импорт, что в `components/ui/accordion.tsx`. Удаление `AccordionTrigger` из импорта согласовано с заменой на кастомный триггер.

---

## Execution Handoff

(Заполняется контроллером при запуске.) Рекомендация по моделям (как в прошлом срезе): Task 1 — Sonnet (бэкенд), Task 2 — Haiku (чистые функции), Task 3 — Sonnet (интеграция + кастомный Radix), Task 4 — Haiku (доки); оркестрация+ревью — Opus.
