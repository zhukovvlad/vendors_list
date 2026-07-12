# Карточка вендора: редизайн + инлайн-правка шапки — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести карточку вендора до утверждённого визуального дизайна (карточки-поверхности по макету) и добавить инлайн-правку имени (в `<h1>`) и примечания.

**Architecture:** Редизайн — рестайл существующего `VendorCardScreen` в карточки-поверхности на семантических токенах DS (сырые hex макета → токены, тема-агностично). Инлайн-правка — новый `PATCH /vendors/{id}` (partial-семантика, rename→alias, коллизии→409) + изолированный компонент `InlineEditText` (Notion/Linear-паттерн) + хук с инвалидацией трёх queryKey. Сначала вёрстка, поверх — правка.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy Core (async), PostgreSQL; Vite + React + TS, shadcn/ui + Tailwind (токены), TanStack Router/Query, vitest + MSW.

Спека: [docs/superpowers/specs/2026-07-12-vendor-card-polish-inline-edit-design.md](../specs/2026-07-12-vendor-card-polish-inline-edit-design.md).

## Global Constraints

Каждая задача неявно наследует (CLAUDE.md «Золотые правила»):

- **Schema-first, без ORM.** Только SQLAlchemy Core (`text(...)`).
- **Пишущие эндпоинты — только через `Depends(tx)`** (ставит `app.user`); правки — `Depends(require_admin)`, viewer → 403. Читающие — `Depends(require_user)` + `Depends(read_conn)`.
- **Только семантические токены DS. Новых токенов НЕ заводить.** Осознанные упрощения относительно макета (принято заказчиком): серый ramp `#76728C`/`#534F68` → `text-muted-foreground`; акцент → `text-primary` (не `primary-hover`); делители/радиус-6px → `border-border`/`rounded-md`; **шеврон аккордеона — штатный трейлинг shadcn** (макетный leading-акцентный не воспроизводим, DS-примитив не форкаем).
- **UI только на русском.** Локализация значений enum — на фронте.
- **`main` зелёный:** ветка `feat/vendor-card-polish` (создана, спека закоммичена), `just ci` зелёный перед PR, мерж через PR.
- **Типы сквозные:** после правок бэкенд-контракта — `just types` (регенерит `frontend/src/api/schema.d.ts`, gitignored).
- **db-тесты (маркер `db`)** идут на тест-ветке Neon; `DATABASE_URL_TEST` присутствует локально. Новую ревизию БД срез НЕ добавляет (миграций нет).

## Токены (сопоставление макета, для §вёрстки)

`bg-card` (#16121F), `border-border` (#2A2640), `bg-accent` (#1E1930, elevated-подложка), `bg-muted` (#110D1C, sunken-легенда), `border-border-strong border-dashed` (#3A3556, пунктир), `text-primary` (акцент), `text-muted-foreground` (вторичный), `text-foreground` (основной), `rounded-xl` (10px карточки/аватар), `rounded-md` (4px чипы), `rounded-full` (пилюли). Иконки lucide: `Award`, `Merge`, `Plus`, `Star`, `X`.

---

## Файловая структура

**Создать:**
- `frontend/src/screens/vendors/InlineEditText.tsx` — изолированный компонент инлайн-правки.
- `frontend/src/screens/vendors/InlineEditText.test.tsx` — юниты компонента.

**Изменить:**
- `backend/app/schemas/__init__.py` — схема `VendorHeaderUpdate`.
- `backend/app/routers/vendors.py` — рефактор `_load_vendor_card` + эндпоинт `PATCH /vendors/{id}`.
- `backend/tests/api/test_vendors.py` — api-тесты PATCH.
- `frontend/src/screens/vendors/model.ts` — хелперы `pluralStandards`, `pluralVendors`, `avatarInitial`.
- `frontend/src/screens/vendors/model.test.ts` — юниты новых хелперов.
- `frontend/src/screens/vendors/VendorCardScreen.tsx` — редизайн (Task 2) + инлайн-правка (Task 4).
- `frontend/src/screens/vendors/VendorCardScreen.test.tsx` — тесты редизайна и правки.
- `frontend/src/api/queries.ts` — хук `useUpdateVendorHeader`.
- `CLAUDE.md`, `docs/TECH_DEBT.md`, `docs/devlog/2026-07-12-vendor-card-polish.md` (Task 5).

---

## Task 1: Бэкенд — `PATCH /vendors/{id}` (имя+примечание, rename→alias, коллизии→409)

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/routers/vendors.py`
- Test: `backend/tests/api/test_vendors.py`

**Interfaces:**
- Consumes: `_ensure_vendor`, `VendorAlias`/`VendorRepresents`/`VendorCard`, `require_admin`/`CurrentUser`/`tx`, `IntegrityError` (уже в `vendors.py`); фабрики `make_vendor`/`make_alias`, фикстуры `client`/`as_admin`/`as_viewer`/`db_conn`.
- Produces: `PATCH /vendors/{vendor_id}` → `VendorCard`; Pydantic `VendorHeaderUpdate {name?: str, note?: str|None}`; хелпер `_load_vendor_card(conn, vendor_id) -> VendorCard`.

- [ ] **Step 1: Схема `VendorHeaderUpdate`**

В `backend/app/schemas/__init__.py` убедиться, что импортирован `field_validator` (строка импорта pydantic: `from pydantic import BaseModel, ConfigDict, Field, field_validator`), затем добавить в конец файла:

```python
class VendorHeaderUpdate(BaseModel):
    """Инлайн-правка шапки. Partial: в эндпоинте читаем model_dump(exclude_unset=True),
    чтобы отличить «поле не пришло» от «note: null (очистить)»."""

    name: str | None = None
    note: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Имя не может быть пустым")
        return stripped
```

- [ ] **Step 2: Рефактор — вынести `_load_vendor_card`**

В `backend/app/routers/vendors.py` заменить тело `get_vendor` на вызов нового хелпера. Добавить хелпер (перед `get_vendor`) и упростить эндпоинт:

```python
async def _load_vendor_card(conn: AsyncConnection, vendor_id: int) -> VendorCard:
    """Собирает VendorCard из готовых объектов БД (starred — из vendor_starred).
    404, если вендора нет. Переиспользуется в GET и PATCH."""
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
        represented_count=represented_count,
        represents=represents,
        aliases=aliases,
    )


@router.get("/{vendor_id}", response_model=VendorCard, dependencies=[Depends(require_user)])
async def get_vendor(vendor_id: int, conn: AsyncConnection = Depends(read_conn)) -> VendorCard:
    return await _load_vendor_card(conn, vendor_id)
```

Добавить `VendorHeaderUpdate` в существующий импорт `from ..schemas import (...)`.

- [ ] **Step 3: Написать падающие api-тесты PATCH**

В начало `backend/tests/api/test_vendors.py` уже импортирован `text` (из Task 7). Добавить тесты в конец файла:

```python
async def _aliases(db_conn, vendor_id: int) -> list[str]:
    return [
        r["alias"]
        for r in (
            await db_conn.execute(
                text("SELECT alias FROM vendor_alias WHERE vendor_id = :v ORDER BY alias"),
                {"v": vendor_id},
            )
        ).mappings()
    ]


async def _name(db_conn, vendor_id: int) -> str:
    return (
        await db_conn.execute(text("SELECT name FROM vendor WHERE id = :v"), {"v": vendor_id})
    ).scalar_one()


async def _note(db_conn, vendor_id: int) -> str | None:
    return (
        await db_conn.execute(text("SELECT note FROM vendor WHERE id = :v"), {"v": vendor_id})
    ).scalar_one()


async def test_patch_name_moves_old_to_alias(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="Старое имя")
    resp = await client.patch(f"/vendors/{v}", json={"name": "Новое имя"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Новое имя"
    assert await _name(db_conn, v) == "Новое имя"
    assert "Старое имя" in await _aliases(db_conn, v)  # пр.1: старое имя → алиас


async def test_patch_name_round_trip_alias_state(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="A")
    await client.patch(f"/vendors/{v}", json={"name": "B"})
    await client.patch(f"/vendors/{v}", json={"name": "A"})
    # пр.1: конечное состояние — name=A, алиасы ровно {B} (мусор не накопился)
    assert await _name(db_conn, v) == "A"
    assert await _aliases(db_conn, v) == ["B"]


async def test_patch_name_duplicate_vendor_name_409(client, as_admin, db_conn) -> None:
    a = await f.make_vendor(db_conn, name="Alpha")
    await f.make_vendor(db_conn, name="Beta")
    resp = await client.patch(f"/vendors/{a}", json={"name": "Beta"})
    assert resp.status_code == 409


async def test_patch_name_clash_with_other_alias_409(client, as_admin, db_conn) -> None:
    owner = await f.make_vendor(db_conn, name="Owner")
    await f.make_alias(db_conn, vendor_id=owner, alias="ЗанятыйАлиас")
    v = await f.make_vendor(db_conn, name="Mover")
    resp = await client.patch(f"/vendors/{v}", json={"name": "ЗанятыйАлиас"})
    assert resp.status_code == 409  # пр.2: коллизия имени с чужим алиасом


async def test_patch_note_set_and_clear(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="note-vendor")
    await client.patch(f"/vendors/{v}", json={"note": "заметка"})
    assert await _note(db_conn, v) == "заметка"
    resp = await client.patch(f"/vendors/{v}", json={"note": ""})  # пр.3: "" → NULL
    assert resp.status_code == 200
    assert await _note(db_conn, v) is None


async def test_patch_note_absent_leaves_untouched(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="keep-note")
    await client.patch(f"/vendors/{v}", json={"note": "сохранить"})
    await client.patch(f"/vendors/{v}", json={"name": "keep-note-2"})  # note не в теле
    assert await _note(db_conn, v) == "сохранить"  # пр.3: поле не пришло → не трогаем


async def test_patch_blank_name_422(client, as_admin, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="blank-name")
    resp = await client.patch(f"/vendors/{v}", json={"name": "   "})
    assert resp.status_code == 422


async def test_patch_missing_vendor_404(client, as_admin) -> None:
    resp = await client.patch("/vendors/999999", json={"name": "x"})
    assert resp.status_code == 404


async def test_patch_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    v = await f.make_vendor(db_conn, name="patch-viewer")
    resp = await client.patch(f"/vendors/{v}", json={"name": "nope"})
    assert resp.status_code == 403
```

- [ ] **Step 4: Прогнать — падают (эндпоинта нет)**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -k patch -v`
Expected: FAIL (405/404 — маршрута PATCH нет).

- [ ] **Step 5: Реализовать эндпоинт PATCH**

В `backend/app/routers/vendors.py` добавить (после `remove_alias`):

```python
@router.patch("/{vendor_id}", response_model=VendorCard)
async def update_vendor_header(
    vendor_id: int,
    body: VendorHeaderUpdate,
    _admin: CurrentUser = Depends(require_admin),
    conn: AsyncConnection = Depends(tx),
) -> VendorCard:
    """Инлайн-правка шапки (имя и/или примечание, partial).

    Смена имени нормализует справочник: старое написание уходит в алиасы (пр.1,
    ON CONFLICT — идемпотентно для A→B→A). Коллизия нового имени с чужим именем
    (UNIQUE → IntegrityError) или чужим алиасом (пр.2, явная проверка) → 409.
    note: "" → NULL (пр.3); поле не в теле → не трогаем.
    """
    row = (
        await conn.execute(text("SELECT name FROM vendor WHERE id = :id"), {"id": vendor_id})
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вендор не найден")
    data = body.model_dump(exclude_unset=True)

    if "name" in data:
        new_name = data["name"]  # уже стрипнуто валидатором
        old_name = row["name"]
        if new_name != old_name:
            clash = (
                await conn.execute(
                    text("SELECT 1 FROM vendor_alias WHERE alias = :n AND vendor_id <> :id"),
                    {"n": new_name, "id": vendor_id},
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Имя уже занято")
            # снять дубль «новое имя == собственный алиас»
            await conn.execute(
                text("DELETE FROM vendor_alias WHERE vendor_id = :id AND alias = :n"),
                {"id": vendor_id, "n": new_name},
            )
            try:
                await conn.execute(
                    text("UPDATE vendor SET name = :n WHERE id = :id"),
                    {"n": new_name, "id": vendor_id},
                )
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "Имя уже занято") from exc
            # старое имя → алиас (идемпотентно)
            await conn.execute(
                text(
                    "INSERT INTO vendor_alias (vendor_id, alias) VALUES (:id, :old) "
                    "ON CONFLICT (alias) DO NOTHING"
                ),
                {"id": vendor_id, "old": old_name},
            )

    if "note" in data:
        raw = data["note"]
        note = raw.strip() if raw else None
        note = note or None
        await conn.execute(
            text("UPDATE vendor SET note = :note WHERE id = :id"),
            {"note": note, "id": vendor_id},
        )

    return await _load_vendor_card(conn, vendor_id)
```

- [ ] **Step 6: Прогнать — PASS + типы**

Run: `cd backend; uv run pytest tests/api/test_vendors.py -v` — Expected: PASS (все тесты вендора, старые + 9 новых PATCH).
Run: `just types` — Expected: `schema.d.ts` содержит `patch` для `/vendors/{vendor_id}`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/routers/vendors.py backend/tests/api/test_vendors.py
git commit -m "feat(api): PATCH /vendors/{id} — инлайн-правка имени/note (rename→alias, коллизии 409)"
```

> `schema.d.ts` gitignored — не стейджим, регенерится в CI.

---

## Task 2: Редизайн карточки — карточки-поверхности по макету

**Files:**
- Modify: `frontend/src/screens/vendors/model.ts`
- Modify: `frontend/src/screens/vendors/model.test.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: существующие хуки/хелперы (`useVendor`, `useVendorWhereAllowed`, `useToggleAgreement`, `useAddAlias`, `useRemoveAlias`, `kindLabel`, `pluralPositions`, `excludedTooltip`, `WHERE_ALLOWED_EMPTY`, `whereAllowedLegend`, `hasExcludedChips`).
- Produces: хелперы `pluralStandards(n)`, `pluralVendors(n)`, `avatarInitial(name)`. Рестайленный `VendorCardScreen` (имя/note пока статичны — инлайн-правка в Task 4).

- [ ] **Step 1: Хелперы + падающие юниты**

В `frontend/src/screens/vendors/model.ts` добавить:

```ts
/** Русское склонение «стандарт» по числу. */
export function pluralStandards(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return "стандарт"
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "стандарта"
  return "стандартов"
}

/** Русское склонение «вендор» по числу. */
export function pluralVendors(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return "вендор"
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "вендора"
  return "вендоров"
}

/** Инициал для аватар-плитки: первая непробельная буква имени, заглавная. */
export function avatarInitial(name: string): string {
  const ch = name.trim().charAt(0)
  return ch ? ch.toUpperCase() : "?"
}
```

В `frontend/src/screens/vendors/model.test.ts` добавить импорт `pluralStandards, pluralVendors, avatarInitial` к существующему импорту из `./model` и блок:

```ts
describe("pluralStandards / pluralVendors", () => {
  it("склоняет стандарт", () => {
    expect(`${1} ${pluralStandards(1)}`).toBe("1 стандарт")
    expect(`${3} ${pluralStandards(3)}`).toBe("3 стандарта")
    expect(`${5} ${pluralStandards(5)}`).toBe("5 стандартов")
    expect(`${11} ${pluralStandards(11)}`).toBe("11 стандартов")
  })
  it("склоняет вендор", () => {
    expect(`${1} ${pluralVendors(1)}`).toBe("1 вендор")
    expect(`${2} ${pluralVendors(2)}`).toBe("2 вендора")
    expect(`${7} ${pluralVendors(7)}`).toBe("7 вендоров")
  })
})

describe("avatarInitial", () => {
  it("первая буква заглавная", () => {
    expect(avatarInitial("system air")).toBe("S")
    expect(avatarInitial("  ромашка")).toBe("Р")
  })
  it("пустое имя → ?", () => {
    expect(avatarInitial("   ")).toBe("?")
  })
})
```

Run: `cd frontend; npm run test -- model.test` — Expected: PASS (чистые функции).

- [ ] **Step 2: Обновить/добавить смоук-тесты редизайна**

В `frontend/src/screens/vendors/VendorCardScreen.test.tsx` в `describe("VendorCardScreen — Где разрешён")` заменить пустой сценарий и добавить смоук на сводку и пустое состояние алиасов. Заменить существующий тест «пустой вендор» на версию, дополнительно проверяющую сводку, и добавить тесты сводки/аватара. Вставить в файл (в подходящие describe-блоки):

```tsx
// в describe("VendorCardScreen — шапка")
it("показывает аватар-инициал и пустое состояние алиасов", async () => {
  server.use(
    http.get("/api/vendors/:vendorId", () =>
      HttpResponse.json({ ...vendorFixture, aliases: [] })
    )
  )
  renderAt()
  await screen.findByRole("heading", { level: 1, name: /System Air/ })
  expect(screen.getByText("S")).toBeInTheDocument() // инициал аватара
  expect(screen.getByText("вариантов пока нет")).toBeInTheDocument()
})

// в describe("VendorCardScreen — Где разрешён")
it("показывает сводку «N стандартов · M позиций»", async () => {
  renderAt()
  expect(await screen.findByText("1 стандарт · 1 позиция")).toBeInTheDocument()
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (нет «S»/«вариантов пока нет»/сводки — старая вёрстка).

- [ ] **Step 3: Рестайл `VendorCardScreen.tsx` под макет**

Полностью заменить содержимое `frontend/src/screens/vendors/VendorCardScreen.tsx` (сохраняя ВСЕ существующие хуки и логику toggle/alias/where-allowed; имя и note остаются статичными — Task 4 их заменит на `InlineEditText`):

```tsx
import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { Award, Merge, Plus, Star, X } from "lucide-react"

import {
  useAddAlias,
  useRemoveAlias,
  useToggleAgreement,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import {
  avatarInitial,
  excludedTooltip,
  hasExcludedChips,
  kindLabel,
  pluralPositions,
  pluralStandards,
  pluralVendors,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"

const CARD = "rounded-xl border border-border bg-card"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)
  const whereAllowed = useVendorWhereAllowed(id)
  const toggleAgreement = useToggleAgreement(id)
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")

  if (isPending)
    return (
      <div className="py-16 text-center text-muted-foreground">Загрузка…</div>
    )
  if (isError || !data)
    return (
      <div className="py-16 text-center text-muted-foreground">
        Вендор не найден
      </div>
    )

  const standards = whereAllowed.data?.standards ?? []
  const positionTotal = standards.reduce((a, s) => a + s.position_count, 0)

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-3 py-6">
      {/* Шапка */}
      <section className={`${CARD} px-5 py-[18px]`}>
        <div className="flex items-center gap-3.5">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-border bg-accent text-h4 font-medium text-primary">
            {avatarInitial(data.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-h3 font-medium tracking-tight">{data.name}</h1>
              <Badge variant="outline" className="rounded-full">
                {kindLabel(data.kind)}
              </Badge>
              {data.starred && (
                <Badge variant="outline" className="gap-1 rounded-full">
                  <Star className="size-3 fill-current" aria-hidden />
                  соглашение
                </Badge>
              )}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-small text-muted-foreground">
              <Award className="size-3.5 shrink-0" aria-hidden />
              {data.represents ? (
                <span>
                  представляет:{" "}
                  <Link
                    to="/vendors/$vendorId"
                    params={{ vendorId: String(data.represents.id) }}
                    className="underline"
                  >
                    {data.represents.name}
                  </Link>
                </span>
              ) : (
                "самостоятельный бренд"
              )}
            </div>
            {data.note && (
              <p
                data-testid="vendor-note"
                className="mt-1 text-small text-muted-foreground"
              >
                {data.note}
              </p>
            )}
          </div>
          <label className="flex shrink-0 items-center gap-2 text-small text-muted-foreground">
            Соглашение
            <Switch
              checked={data.starred}
              disabled={toggleAgreement.isPending}
              onCheckedChange={(next) => toggleAgreement.mutate(next)}
              aria-label="Соглашение о сотрудничестве"
            />
          </label>
        </div>
      </section>

      {/* Варианты написания */}
      <section className={`${CARD} px-5 py-[15px]`}>
        <div className="mb-2.5 text-caption uppercase text-muted-foreground">
          Варианты написания
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">
              вариантов пока нет
            </span>
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
                className="h-7 rounded-md border border-border bg-transparent px-2 text-small"
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
            <button
              type="button"
              onClick={() => setAliasOpen(true)}
              className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-strong px-2.5 py-1 text-small text-primary"
            >
              <Plus className="size-3" aria-hidden />
              вариант
            </button>
          )}
        </div>
      </section>

      {/* Бренд и объединение */}
      <section className={`${CARD} px-5 py-[15px]`}>
        <div className="mb-2.5 text-caption uppercase text-muted-foreground">
          Бренд и объединение
        </div>
        <div className="flex items-center gap-2.5">
          <Award className="size-4 shrink-0 text-primary" aria-hidden />
          <div className="flex-1 text-small">
            {data.represents ? (
              <>
                Представляет:{" "}
                <Link
                  to="/vendors/$vendorId"
                  params={{ vendorId: String(data.represents.id) }}
                  className="underline"
                >
                  {data.represents.name}
                </Link>
              </>
            ) : (
              <>
                Самостоятельный бренд
                <div className="text-caption text-muted-foreground">
                  {data.represented_count > 0
                    ? `${data.represented_count} ${pluralVendors(
                        data.represented_count
                      )} представляют этот бренд`
                    : "не представляет другого вендора"}
                </div>
              </>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled
            className="gap-1.5"
            title="в разработке"
          >
            <Merge className="size-3.5" aria-hidden />
            Объединить
            <span className="text-caption text-muted-foreground">· скоро</span>
          </Button>
        </div>
      </section>

      {/* Где разрешён */}
      <section className={`${CARD} px-5 py-[15px]`}>
        <div className="flex items-baseline justify-between">
          <span className="text-caption uppercase text-muted-foreground">
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
          <div className="mt-2 text-small text-muted-foreground">Загрузка…</div>
        ) : whereAllowed.isError ? (
          <div className="mt-2 text-small text-muted-foreground">
            Не удалось загрузить
          </div>
        ) : standards.length === 0 ? (
          <div className="mt-2 text-small text-muted-foreground">
            {WHERE_ALLOWED_EMPTY}
          </div>
        ) : (
          <>
            <Accordion type="multiple" className="mt-2">
              {standards.map((s) => (
                <AccordionItem
                  key={s.building_type_id}
                  value={String(s.building_type_id)}
                >
                  <AccordionTrigger>
                    <span className="flex-1 text-left">
                      {s.building_type_name}
                    </span>
                    <span className="mr-2 text-small text-muted-foreground">
                      {`${s.position_count} ${pluralPositions(s.position_count)}`}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="ml-6 border-l border-border pl-4">
                    <div className="space-y-3">
                      {s.positions.map((p) => (
                        <div key={p.position_id} className="space-y-1.5">
                          <div className="text-small">{p.position_name}</div>
                          <div className="flex flex-wrap gap-1.5">
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
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
            <p className="mt-2.5 rounded-md border border-border bg-muted px-3 py-2 text-caption text-muted-foreground">
              {whereAllowedLegend(hasExcludedChips(standards))}
            </p>
          </>
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Прогнать — PASS + typecheck + format**

Run: `cd frontend; npm run test -- VendorCardScreen model.test` — Expected: PASS.
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.
Run: `cd frontend; npm run format` затем `npm run format:check` — Expected: чисто.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/vendors/model.ts frontend/src/screens/vendors/model.test.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): редизайн карточки — карточки-поверхности, аватар, сводка, пустые состояния (токены)"
```

---

## Task 3: Компонент `InlineEditText`

**Files:**
- Create: `frontend/src/screens/vendors/InlineEditText.tsx`
- Test: `frontend/src/screens/vendors/InlineEditText.test.tsx`

**Interfaces:**
- Produces: `InlineEditText` — пропсы `{ value: string; onSubmit: (next: string) => Promise<void> | void; ariaLabel: string; multiline?: boolean; placeholder?: string; error?: string | null; onEditStart?: () => void; displayClassName?: string; inputClassName?: string }`. Поведение: клик по дисплею → правка; single Enter/blur сохраняют, Esc отменяет; multiline blur сохраняет, Esc отменяет; no-op (draft==value) и single+пусто → без вызова `onSubmit`; reject `onSubmit` → остаёмся в правке; `error` рисуется под полем (`role="alert"`).

- [ ] **Step 1: Падающие юниты**

Create `frontend/src/screens/vendors/InlineEditText.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { InlineEditText } from "./InlineEditText"

describe("InlineEditText", () => {
  it("клик по дисплею открывает инпут со значением", async () => {
    render(<InlineEditText value="Имя" onSubmit={vi.fn()} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    expect(screen.getByRole("textbox")).toHaveValue("Имя")
  })

  it("Enter сохраняет новое значение", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<InlineEditText value="Старое" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Старое" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.type(screen.getByRole("textbox"), "Новое{Enter}")
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith("Новое")
  })

  it("Esc отменяет, onSubmit не зовётся, возврат к дисплею", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.type(screen.getByRole("textbox"), "xxx")
    await userEvent.keyboard("{Escape}")
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Имя" })).toBeInTheDocument()
  })

  it("no-op: значение не изменилось → onSubmit не зовётся", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("single + пусто → отмена (имя обязательно)", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("reject onSubmit → остаёмся в правке, error виден", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("409"))
    const { rerender } = render(
      <InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" error={null} />
    )
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.type(screen.getByRole("textbox"), "Занято{Enter}")
    rerender(
      <InlineEditText
        value="Имя"
        onSubmit={onSubmit}
        ariaLabel="Имя"
        error="Имя уже занято"
      />
    )
    expect(screen.getByRole("textbox")).toBeInTheDocument() // не вышли из правки
    expect(screen.getByRole("alert")).toHaveTextContent("Имя уже занято")
  })

  it("multiline: Enter не сохраняет, blur сохраняет", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <InlineEditText
        value=""
        onSubmit={onSubmit}
        ariaLabel="Примечание"
        multiline
        placeholder="+ примечание"
      />
    )
    await userEvent.click(screen.getByRole("button", { name: "Примечание" }))
    await userEvent.type(screen.getByRole("textbox"), "строка{Enter}ещё")
    expect(onSubmit).not.toHaveBeenCalled() // Enter — перенос строки
    await userEvent.tab() // blur
    expect(onSubmit).toHaveBeenCalledOnce()
  })
})
```

Run: `cd frontend; npm run test -- InlineEditText` — Expected: FAIL (компонента нет).

- [ ] **Step 2: Реализовать `InlineEditText`**

Create `frontend/src/screens/vendors/InlineEditText.tsx`:

```tsx
import { useRef, useState } from "react"

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
}

/**
 * Инлайн-правка текста (Notion/Linear): клик по дисплею → поле на месте.
 * single: Enter/blur сохраняют, Esc отменяет; multiline: blur сохраняет, Esc
 * отменяет (Enter — перенос строки). No-op (draft==value) и single+пусто не
 * зовут onSubmit. Reject onSubmit → остаёмся в правке (ошибку рисует родитель
 * через `error`). doneRef гарантирует один commit на сессию (Enter+последующий
 * blur не дают двойного сохранения).
 */
export function InlineEditText({
  value,
  onSubmit,
  ariaLabel,
  multiline = false,
  placeholder,
  error,
  onEditStart,
  displayClassName,
  inputClassName,
}: InlineEditTextProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const doneRef = useRef(false)

  function startEdit() {
    doneRef.current = false
    setDraft(value)
    onEditStart?.()
    setEditing(true)
  }

  async function commit() {
    if (doneRef.current) return
    const next = draft.trim()
    if (next === value.trim() || (!multiline && next === "")) {
      doneRef.current = true
      setEditing(false)
      return
    }
    doneRef.current = true
    setSaving(true)
    try {
      await onSubmit(multiline ? draft : next)
      setEditing(false)
    } catch {
      doneRef.current = false // разрешаем повтор; остаёмся в правке
    } finally {
      setSaving(false)
    }
  }

  function cancel() {
    doneRef.current = true
    setEditing(false)
  }

  if (!editing) {
    const empty = value.trim() === ""
    return (
      <button
        type="button"
        onClick={startEdit}
        aria-label={ariaLabel}
        className={displayClassName}
      >
        {empty ? (placeholder ?? "") : value}
      </button>
    )
  }

  const shared = {
    autoFocus: true,
    value: draft,
    disabled: saving,
    "aria-label": ariaLabel,
    "aria-invalid": error ? true : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setDraft(e.target.value),
    onBlur: () => {
      void commit()
    },
    className: inputClassName,
  }

  return (
    <span className="inline-flex flex-col">
      {multiline ? (
        <textarea
          {...shared}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
          }}
        />
      ) : (
        <input
          {...shared}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              void commit()
            } else if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
          }}
        />
      )}
      {error && (
        <span role="alert" className="mt-1 text-caption text-destructive">
          {error}
        </span>
      )}
    </span>
  )
}
```

- [ ] **Step 3: Прогнать — PASS + typecheck**

Run: `cd frontend; npm run test -- InlineEditText` — Expected: PASS (7 тестов).
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/vendors/InlineEditText.tsx frontend/src/screens/vendors/InlineEditText.test.tsx
git commit -m "feat(vendors): компонент InlineEditText — инлайн-правка текста (Notion/Linear-паттерн)"
```

---

## Task 4: Инлайн-правка в шапке — хук + интеграция имени и примечания

**Files:**
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.tsx`
- Modify: `frontend/src/screens/vendors/VendorCardScreen.test.tsx`

**Interfaces:**
- Consumes: `PATCH /vendors/{id}` (Task 1), `InlineEditText` (Task 3), существующая шапка (Task 2).
- Produces: `useUpdateVendorHeader(id)` → мутация `(fields: { name?: string; note?: string }) => VendorCard`, `onSuccess` инвалидирует `["vendor", id]` + `["matrix"]` + `["dashboard"]`.

- [ ] **Step 1: Хук `useUpdateVendorHeader`**

В `frontend/src/api/queries.ts` добавить (после `useRemoveAlias`):

```ts
/**
 * Мутация инлайн-правки шапки (имя/примечание, partial). На успехе инвалидирует
 * карточку, а также матрицу и дашборд (имя вендора видно в обоих).
 */
export function useUpdateVendorHeader(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (fields: { name?: string; note?: string }) => {
      const { data, error } = await api.PATCH("/vendors/{vendor_id}", {
        params: { path: { vendor_id: id } },
        body: fields,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor", id] })
      qc.invalidateQueries({ queryKey: ["matrix"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}
```

- [ ] **Step 2: Падающие тесты интеграции**

В `frontend/src/screens/vendors/VendorCardScreen.test.tsx` добавить блок:

```tsx
describe("VendorCardScreen — инлайн-правка шапки", () => {
  it("клик по имени → инпут в h1; Enter шлёт PATCH {name}", async () => {
    let patched: unknown = null
    server.use(
      http.patch("/api/vendors/:vendorId", async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...vendorFixture, name: "System Air 2" })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать имя" })
    )
    const input = screen.getByRole("textbox", { name: "Редактировать имя" })
    await userEvent.clear(input)
    await userEvent.type(input, "System Air 2{Enter}")
    await waitFor(() => expect(patched).toEqual({ name: "System Air 2" }))
    // инпут имени живёт внутри h1 (пр.4)
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument()
  })

  it("409 на имени → инлайн-ошибка, остаёмся в правке", async () => {
    server.use(
      http.patch("/api/vendors/:vendorId", () =>
        HttpResponse.json({ detail: "Имя уже занято" }, { status: 409 })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать имя" })
    )
    const input = screen.getByRole("textbox", { name: "Редактировать имя" })
    await userEvent.clear(input)
    await userEvent.type(input, "Занятое{Enter}")
    expect(await screen.findByRole("alert")).toHaveTextContent("Имя уже занято")
    expect(
      screen.getByRole("textbox", { name: "Редактировать имя" })
    ).toBeInTheDocument()
  })

  it("правка примечания шлёт PATCH {note}", async () => {
    let patched: unknown = null
    server.use(
      http.patch("/api/vendors/:vendorId", async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...vendorFixture, note: "заметка" })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать примечание" })
    )
    await userEvent.type(
      screen.getByRole("textbox", { name: "Редактировать примечание" }),
      "заметка"
    )
    await userEvent.tab() // blur сохраняет
    await waitFor(() => expect(patched).toEqual({ note: "заметка" }))
  })
})
```

Run: `cd frontend; npm run test -- VendorCardScreen` — Expected: FAIL (имя/note ещё статичны).

- [ ] **Step 3: Интегрировать `InlineEditText` в шапку**

В `frontend/src/screens/vendors/VendorCardScreen.tsx`:

1) Импорты — добавить компонент, хук и `useState` уже есть:

```tsx
import { useUpdateVendorHeader } from "@/api/queries"   // добавить к существующему импорту из "@/api/queries"
import { InlineEditText } from "./InlineEditText"
```

2) В теле компонента — мутация и локальная ошибка имени:

```tsx
  const updateHeader = useUpdateVendorHeader(id)
  const [nameError, setNameError] = useState<string | null>(null)
```

3) Заменить статический `<h1>` с именем на инлайн-правку (кнопка/инпут ЖИВУТ ВНУТРИ `<h1>` — пр.4):

```tsx
              <h1 className="min-w-0 text-h3 font-medium tracking-tight">
                <InlineEditText
                  value={data.name}
                  ariaLabel="Редактировать имя"
                  onEditStart={() => setNameError(null)}
                  error={nameError}
                  displayClassName="max-w-full truncate text-left hover:opacity-80"
                  inputClassName="w-full rounded-md border border-border bg-transparent px-1 text-h3 font-medium outline-none focus-visible:border-ring"
                  onSubmit={async (next) => {
                    setNameError(null)
                    try {
                      await updateHeader.mutateAsync({ name: next })
                    } catch (e) {
                      // Единственный ожидаемый отказ правки имени — 409 (занято);
                      // прочее маловероятно, сообщение по сути не вводит в заблуждение.
                      setNameError("Имя уже занято")
                      throw e
                    }
                  }}
                />
              </h1>
```

> `mutateAsync` бросает при HTTP-ошибке (хук делает `throw error`); ловим, ставим `nameError`, ре-throw — `InlineEditText` остаётся в правке. Любая ошибка правки имени для пользователя = «Имя уже занято» (единственный ожидаемый отказ — 409; прочее маловероятно и сообщение не вводит в заблуждение по сути).

4) Заменить статический блок примечания (`{data.note && <p .../>}`) на инлайн-правку с плейсхолдером:

```tsx
            <div className="mt-1 text-small text-muted-foreground">
              <InlineEditText
                value={data.note ?? ""}
                ariaLabel="Редактировать примечание"
                multiline
                placeholder="+ примечание"
                displayClassName="text-left hover:text-foreground"
                inputClassName="w-full rounded-md border border-border bg-transparent px-1 py-0.5 text-small outline-none focus-visible:border-ring"
                onSubmit={async (next) => {
                  await updateHeader.mutateAsync({ note: next })
                }}
              />
            </div>
```

> Примечание не даёт инлайн-ошибки (нет уникальности); при сбое просто останется в правке. При стирании текста `InlineEditText` для multiline отдаёт пустую строку → PATCH `{note: ""}` → бэкенд пишет `NULL` (пр.3). Плейсхолдер «+ примечание» рисует сам `InlineEditText`, когда `value` пуст.

- [ ] **Step 4: Прогнать — PASS + typecheck + format**

Run: `cd frontend; npm run test -- VendorCardScreen InlineEditText model.test` — Expected: PASS.
Run: `cd frontend; npm run typecheck` — Expected: без ошибок.
Run: `cd frontend; npm run format` затем `npm run format:check` — Expected: чисто.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/screens/vendors/VendorCardScreen.tsx frontend/src/screens/vendors/VendorCardScreen.test.tsx
git commit -m "feat(vendors): инлайн-правка имени (в h1) и примечания — PATCH, 409-инлайн, инвалидация"
```

---

## Task 5: Финализация — `just ci`, документация, PR

**Files:**
- Modify: `CLAUDE.md`, `docs/TECH_DEBT.md`
- Create: `docs/devlog/2026-07-12-vendor-card-polish.md`

- [ ] **Step 1: Полный прогон CI**

Run: `just ci`
Expected: `OK: все проверки прошли`. Если db-тесты скипаются без `DATABASE_URL_TEST` — ок (прогонятся в CI). Если красно — STOP, чинить, не писать доки поверх красного.

- [ ] **Step 2: TECH_DEBT**

В `docs/TECH_DEBT.md` в раздел карточки вендора:
- Убрать/закрыть пункт про кривую RU-copy «N брендов представлены этим» — исправлено в Task 2 (`представляют этот бренд` + `pluralVendors`).
- Добавить: **C2 — сегменты соцобъектов.** Тип «Социальные объекты» имеет 1 сегмент с именем самого типа (заглушка сида); чип класса с именем типа выглядит багом. Показ одноклассовых стандартов — продуктовая развилка (нужна судьба сегментации соцобъектов). В карточке пока рисуется как есть.
- Добавить: **C1 — чистка ~47 грязных имён после сида** (висящие кавычки, `(Native)`) — запланированный follow-up-срез: one-off нормализация ЧЕРЕЗ ту же механику rename→alias из `PATCH /vendors/{id}` (грязное написание → alias, чистое каноническое имя), с ручной сверкой маппинга человеком (ловушка ТЗ §3.4).

- [ ] **Step 3: CLAUDE.md**

- Карта репо: `screens/vendors/` — добавить `InlineEditText` (инлайн-правка) + хелперы `pluralStandards`/`pluralVendors`/`avatarInitial`; роутер `vendors` — эндпоинт `PATCH /vendors/{id}` (правка имени/note, rename→alias) + хелпер `_load_vendor_card`.
- §5: отметить, что карточка вендора доведена до утверждённого дизайна + инлайн-правка шапки (имя/note).

- [ ] **Step 4: Devlog**

Create `docs/devlog/2026-07-12-vendor-card-polish.md` — хронология: редизайн на семантические токены (маппинг сырых hex макета, честный список осознанных упрощений — серый ramp/акцент/шеврон-аккордеона); `PATCH` с partial-семантикой (`exclude_unset`), rename→alias (`DELETE` своего совпавшего алиаса → `UPDATE` → `INSERT ... ON CONFLICT` — идемпотентность A→B→A, покрыта тестом конечного состояния), коллизия имя-vs-чужой-alias; `InlineEditText` (Notion/Linear, `doneRef` против двойного commit на Enter+blur, h1-семантика), инвалидация трёх queryKey; C1/C2 как follow-up.

- [ ] **Step 5: Commit + push + PR**

```bash
git add CLAUDE.md docs/TECH_DEBT.md docs/devlog/2026-07-12-vendor-card-polish.md
git commit -m "docs(vendor-card-polish): devlog + CLAUDE.md карта/§5 + TECH_DEBT (C1 follow-up, C2)"
git push -u origin feat/vendor-card-polish
gh pr create --base main --title "feat: редизайн карточки вендора + инлайн-правка шапки" --body "..."
```

---

## Self-Review

**Spec coverage:**
- §A редизайн (поверхности, шапка+аватар, пустые состояния, «Объединить · скоро», аккордеон/легенда-sunken, маппинг токенов) → Task 2. ✓ (шеврон-leading — осознанное отклонение, зафиксировано в Global Constraints.)
- §B бэкенд PATCH (partial `exclude_unset`, rename→alias пр.1 с `ON CONFLICT` и `DELETE` своего алиаса, коллизия имя+чужой-alias пр.2, note "" → NULL / absent пр.3, `_load_vendor_card`) → Task 1. ✓
- §C фронт (`InlineEditText`, h1-семантика пр.4, хук+инвалидация трёх ключей, note-плейсхолдер, 409-инлайн, no-op/пусто) → Task 3+4. ✓
- Тесты: A→B→A конечное состояние алиасов, коллизии, note два кейса, 422/404/403 → Task 1; юниты компонента + интеграция → Task 3/4. ✓
- C1/C2 follow-up зафиксированы → Task 5 (TECH_DEBT). ✓

**Placeholder scan:** код полный в каждом шаге; «...» только в `gh pr create --body` (Task 5). Явных TODO/TBD нет.

**Type consistency:** `VendorHeaderUpdate {name?, note?}` ↔ хук `useUpdateVendorHeader` body `{name?, note?}` ↔ тесты `{name}`/`{note}`. `_load_vendor_card` возвращает `VendorCard` (та же схема, что GET). `InlineEditText` пропсы согласованы между Task 3 (определение) и Task 4 (использование). queryKey `["vendor", id]`/`["matrix"]`/`["dashboard"]` совпадают с существующими. Хелперы `pluralStandards`/`pluralVendors`/`avatarInitial` определены в Task 2 и там же используются.

---

## Execution Handoff

(Заполняется контроллером при запуске.)
