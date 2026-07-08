# MR Design System Integration (foundation) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Внедрить токены/темы/шрифты MR Design System во фронтенд поверх shadcn/ui, чтобы все компоненты перекрашивались через переменные shadcn, работали светлая и тёмная темы, и реколорить существующий `button` под тона DS.

**Architecture:** Подход **Bridge** — DS-примитивы и «экстра» (бренд-цвета, типографика, тени, радиусы) кладём в `@theme` Tailwind v4; семантику переопределяем на **переменных shadcn** (`--background`, `--primary`, `--card`, `--border`, `--ring`, `--destructive`, `--chart-*`, `--sidebar-*`) в `:root` (светлая) и `.dark` (тёмная). Механизм темы — существующий класс `.dark` (theme-provider не трогаем). `data-theme` не вводим.

**Tech Stack:** Vite + React 19 + TS, Tailwind CSS v4 (CSS-first `@theme`), shadcn/ui (radix-nova, baseColor neutral, cssVariables), vitest + Testing Library. Менеджер команд — `just`.

**Спека:** [docs/superpowers/specs/2026-07-08-design-system-integration-design.md](../specs/2026-07-08-design-system-integration-design.md)

## Global Constraints

- **В `main` не коммитим.** Работаем в ветке `feat/design-system-integration` (уже создана). (Золотое правило №7.)
- **shadcn — основа.** Не вводить второй набор переменных для компонентов; реколор идёт через переменные shadcn. (Золотое правило про UI-стек.)
- **Механизм темы — класс `.dark`**, светлая в `:root`, тёмная в `.dark`. `data-theme` не используем. `theme-provider.tsx` не меняем (дефолт остаётся `system`).
- **Значения — hex из хендоффа** (fidelity hex-exact), в oklch не перегоняем.
- **Вес UI-текста = 400.** Suisse Medium(500) в хендоффе отсутствует; `font-synthesis: none` глобально; акцентный вес — Grtsk.
- **Источник значений:** `temp/design_handoff_mr_design_system_v4/`. Файлы `examples/`, `reference/` в бандл не тянем.
- **Проверка:** каждый таск заканчивается `npm run build` (из `frontend/`) как жёстким гейтом (ловит битые CSS/имена утилит); TS-таск — плюс `npm run lint` и `npm run test`.

## File Structure

- `frontend/src/assets/fonts/` — **создать**: 5 файлов шрифтов (Grtsk Giga Thin/Light/Medium, Suisse Intl Light/Regular). Бандлятся Vite с хешем.
- `frontend/src/styles/fonts.css` — **создать**: `@font-face` (5 объявлений), пути относительно файла.
- `frontend/src/index.css` — **править**: импорт `fonts.css`; `@font-*` в `@theme inline`; фиксированная лесенка радиусов; новый `@theme`-блок DS-экстра (бренд-цвета, типографика, тени); bridge `:root` (светлая) и `.dark` (тёмная); `font-synthesis: none`.
- `frontend/src/components/ui/button-variants.ts` — **править**: радиус, вес, hover primary/outline, новый `subtle`, сплошной `destructive`, disabled в тёмной.
- `frontend/src/components/ui/button.test.tsx` — **править**: добавить ассерты на новые варианты/классы.
- `frontend/src/App.tsx` — **править**: мини-витрина (кнопки всех тонов + swatch'и) для визуальной проверки тем.

Порядок тасков: 1 (шрифты) → 2 (@theme DS-экстра + радиусы) → 3 (bridge) → 4 (button) → 5 (витрина). Таск 4 зависит от bridge-переменных (`--primary-hover`, `--destructive-solid`, `--border-strong`) из таска 3.

---

### Task 1: Самохостинг шрифтов

**Files:**
- Create: `frontend/src/assets/fonts/` (5 файлов, копия из temp)
- Create: `frontend/src/styles/fonts.css`
- Modify: `frontend/src/index.css` (импорт fonts.css; `--font-sans`/`--font-display`/`--font-heading`; `font-synthesis: none`)

**Interfaces:**
- Produces: семейства `"Suisse Intl"` (300/400) и `"Grtsk Giga"` (100/300/500) доступны; `--font-sans` = Suisse-цепочка, `--font-display` = Grtsk; `font-synthesis: none` глобально.

- [ ] **Step 1: Скопировать файлы шрифтов**

Из `temp/design_handoff_mr_design_system_v4/fonts/` в `frontend/src/assets/fonts/` — 5 файлов:
`Grtsk-Giga-Thin.otf`, `GrtskGiga-Light.ttf`, `Grtsk-Giga-Medium.otf`, `SuisseIntl-Light.otf`, `SuisseIntl-Regular.otf`.

Run (из корня репо):
```bash
mkdir -p frontend/src/assets/fonts
cp temp/design_handoff_mr_design_system_v4/fonts/Grtsk-Giga-Thin.otf \
   temp/design_handoff_mr_design_system_v4/fonts/GrtskGiga-Light.ttf \
   temp/design_handoff_mr_design_system_v4/fonts/Grtsk-Giga-Medium.otf \
   temp/design_handoff_mr_design_system_v4/fonts/SuisseIntl-Light.otf \
   temp/design_handoff_mr_design_system_v4/fonts/SuisseIntl-Regular.otf \
   frontend/src/assets/fonts/
ls frontend/src/assets/fonts/
```
Expected: 5 файлов в списке.

- [ ] **Step 2: Создать `frontend/src/styles/fonts.css`**

```css
/* MR Design System — self-hosted font faces.
   Пути относительно этого файла; Vite хеширует и бандлит файлы. */

@font-face {
  font-family: "Grtsk Giga";
  src: url("../assets/fonts/Grtsk-Giga-Thin.otf") format("opentype");
  font-weight: 100;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Grtsk Giga";
  src: url("../assets/fonts/GrtskGiga-Light.ttf") format("truetype");
  font-weight: 300;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Grtsk Giga";
  src: url("../assets/fonts/Grtsk-Giga-Medium.otf") format("opentype");
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Suisse Intl";
  src: url("../assets/fonts/SuisseIntl-Light.otf") format("opentype");
  font-weight: 300;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Suisse Intl";
  src: url("../assets/fonts/SuisseIntl-Regular.otf") format("opentype");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
```

- [ ] **Step 3: Подключить fonts.css в `index.css`**

В `frontend/src/index.css` добавить импорт **пятой строкой**, сразу после существующих `@import` (все `@import` должны идти до остальных правил):

Было (строки 1-4):
```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/inter";
```
Стало — добавить строку:
```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/inter";
@import "./styles/fonts.css";
```

- [ ] **Step 4: Прописать семейства в `@theme inline`**

В `frontend/src/index.css`, блок `@theme inline`, заменить строки шрифтов.

Было:
```css
    --font-heading: var(--font-sans);
    --font-sans: 'Inter Variable', sans-serif;
```
Стало:
```css
    --font-heading: var(--font-display);
    --font-sans: "Suisse Intl", "Inter Variable", system-ui, sans-serif;
    --font-display: "Grtsk Giga", system-ui, sans-serif;
```

- [ ] **Step 5: Отключить синтез начертаний**

В `frontend/src/index.css`, блок `@layer base`, дополнить правило `html`.

Было:
```css
  html {
    @apply font-sans;
    }
```
Стало:
```css
  html {
    @apply font-sans;
    font-synthesis: none;
    }
```

> Оговорка (из спеки): `font-synthesis: none` уберёт синтетический жирный и в контентном тексте с пользовательской разметкой (`<strong>`/`<b>`). Для UI это правильно; точечно включим синтез в контентных зонах позже. На foundation таких зон нет.

- [ ] **Step 6: Сборка (гейт)**

Run (из `frontend/`):
```bash
npm run build
```
Expected: сборка успешна; в `dist/assets/` присутствуют файлы шрифтов с хешем (`SuisseIntl-Regular-*.otf` и т.д.).

- [ ] **Step 7: Визуальная проверка**

Run (из `frontend/`): `npm run dev`, открыть http://localhost:5173.
Expected: текст рендерится гарнитурой Suisse Intl (не Inter, не Times). Заголовок в витрине (появится в Task 5) — Grtsk Giga. Пока витрины нет — достаточно, что основной текст сменил начертание. Faux-bold отсутствует.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/assets/fonts frontend/src/styles/fonts.css frontend/src/index.css
git commit -m "feat(ui): самохостинг шрифтов MR (Grtsk Giga + Suisse Intl)"
```

---

### Task 2: DS-токены в `@theme` + фиксированная лесенка радиусов

**Files:**
- Modify: `frontend/src/index.css` (заменить calc-радиусы `sm/md/lg/xl` в `@theme inline` на фикс. px; добавить `--color-border-strong` и маппинги теней в `@theme inline`; новый `@theme`-блок с бренд-цветами и типографикой)

**Interfaces:**
- Consumes: ничего.
- Produces: утилиты `bg-violet`/`bg-violet-bright`/`bg-violet-deep`/`bg-mint`/`bg-tan`/`bg-lavender`/`text-*`; `border-border-strong`; `text-display`/`text-h1`/`text-h2`/`text-h3`/`text-body-lg`/`text-body`/`text-small`/`text-caption`; `shadow-elevation-1|2|3`/`shadow-glow-violet`/`shadow-focus-ring` (значения приходят из сырых vars `--elevation-*`/`--glow-violet`/`--focus-ring`, задаваемых bridge в Task 3 — тот же механизм, что у цветов); `rounded-sm|md|lg|xl` = 2/4/8/10px. **`--radius` НЕ меняем** (остаётся `0.625rem`): `sm/md/lg/xl` пиннятся фиксированно, поэтому база влияет только на `2xl/3xl/4xl` — их не трогаем, дрейфа нет.

- [ ] **Step 1: Заменить радиусы на фиксированную лесенку DS**

В `frontend/src/index.css`, блок `@theme inline`, заменить четыре calc-строки на фиксированные значения (2xl/3xl/4xl оставить как есть).

Было:
```css
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
```
Стало:
```css
    --radius-sm: 2px;
    --radius-md: 4px;
    --radius-lg: 8px;
    --radius-xl: 10px;
```

- [ ] **Step 2: Добавить маппинги `border-strong` и теней в `@theme inline`**

В том же `@theme inline` добавить строки (значения `--border-strong`/`--elevation-*`/`--glow-violet`/`--focus-ring` придут из bridge в Task 3 — единый механизм с цветами: `@theme inline` мапит на сырую var, тему переключает `:root`/`.dark`):
```css
    --color-border-strong: var(--border-strong);
    --shadow-elevation-1: var(--elevation-1);
    --shadow-elevation-2: var(--elevation-2);
    --shadow-elevation-3: var(--elevation-3);
    --shadow-glow-violet: var(--glow-violet);
    --shadow-focus-ring: var(--focus-ring);
```

> `--radius` **не меняем** — оставляем `0.625rem`. Лесенка `sm/md/lg/xl` пиннится фиксированными px (Step 1), поэтому база `--radius` теперь влияет только на неиспользуемые `2xl/3xl/4xl`; трогать их не нужно, неожиданного дрейфа углов у shadcn-компонентов не будет.

- [ ] **Step 3: Добавить `@theme`-блок DS-экстра (бренд-цвета + типографика)**

В `frontend/src/index.css`, **после** блока `@theme inline` (и до `:root`), добавить новый блок. Тени сюда НЕ кладём — они идут через `@theme inline` + сырые vars (Step 2 + Task 3), как цвета.

```css
@theme {
  /* ---- Brand primitives ---- */
  --color-violet:        #754AE8;
  --color-violet-bright: #8B66F0;
  --color-violet-deep:   #5733C0;
  --color-mint:          #82D6CC;
  --color-tan:           #BD9375;
  --color-lavender:      #E5E3EB;

  /* ---- Typography scale (font-size / line-height / tracking) ---- */
  --text-display: 64px;   --text-display--line-height: 64px;   --text-display--letter-spacing: -0.02em;
  --text-h1:      44px;   --text-h1--line-height: 46px;        --text-h1--letter-spacing: -0.02em;
  --text-h2:      32px;   --text-h2--line-height: 36px;
  --text-h3:      24px;   --text-h3--line-height: 29px;
  --text-body-lg: 18px;   --text-body-lg--line-height: 27px;
  --text-body:    16px;   --text-body--line-height: 26px;
  --text-small:   14px;   --text-small--line-height: 21px;
  --text-caption: 12px;   --text-caption--line-height: 16px;   --text-caption--letter-spacing: 0.08em;
}
```

- [ ] **Step 4: Сборка (гейт)**

Run (из `frontend/`):
```bash
npm run build
```
Expected: сборка успешна (нет ошибок разбора `@theme`, имена утилит валидны).

> Примечание: `border-border-strong` и `shadow-elevation-*` до Task 3 резолвятся в пустые `var(--border-strong)`/`var(--elevation-*)` — это не ошибка сборки; значения появятся с bridge. Пока их никакой компонент не использует.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): DS-токены в @theme (бренд-цвета, типографика, тени, радиусы 2/4/8/10)"
```

---

### Task 3: Bridge — реколор семантики shadcn (light `:root` / dark `.dark`)

**Files:**
- Modify: `frontend/src/index.css` (полностью переписать значения в `:root` и `.dark` на hex DS; добавить `--border-strong`, `--primary-hover`, `--destructive-solid`, `--destructive-foreground`; тёмные тени)

**Interfaces:**
- Consumes: маппинги `@theme inline` (`--color-*: var(--*)`, `--color-border-strong`, `--shadow-*: var(--elevation-*/--glow-violet/--focus-ring)`) из Task 2.
- Produces: переменные shadcn в hex DS для обеих тем; сырые тени `--elevation-1|2|3`/`--glow-violet`/`--focus-ring` (питают `shadow-*`-утилиты); новые bridge-vars `--border-strong`, `--primary-hover`, `--destructive-solid`, `--destructive-foreground`, `--accent-subtle` для Task 4.

- [ ] **Step 1: Переписать `:root` (светлая тема)**

В `frontend/src/index.css` заменить содержимое блока `:root`. Строку `--radius: 0.625rem` оставить без изменений (Task 2 её не трогает). Полный блок:

```css
:root {
    --background: #F4F2FA;
    --foreground: #17131F;
    --card: #FFFFFF;
    --card-foreground: #17131F;
    --popover: #FFFFFF;
    --popover-foreground: #17131F;
    --primary: #754AE8;
    --primary-foreground: #FFFFFF;
    --primary-hover: #5E3AC8;              /* light: акцент темнеет на hover */
    --secondary: #ECEAF4;
    --secondary-foreground: #17131F;
    --muted: #ECEAF4;
    --muted-foreground: #56526B;
    --accent: #ECEAF4;                     /* нейтральный ховер shadcn, НЕ бренд */
    --accent-foreground: #17131F;
    --destructive: #CF4157;                /* мягкие danger: текст/бордер/бейдж */
    --destructive-solid: #CF4157;          /* сплошная danger-кнопка (обе темы) */
    --destructive-foreground: #FFFFFF;
    --accent-subtle: rgba(117, 74, 232, 0.10);  /* подложка subtle-варианта (light) */
    --border: #E4E1EE;
    --border-strong: #CFCADF;
    --input: #E4E1EE;
    --ring: #754AE8;
    --chart-1: #754AE8;
    --chart-2: #158173;
    --chart-3: #9A6636;
    --chart-4: #8471B8;                    /* provisional — финал при чартах */
    --chart-5: #B0A8CC;                    /* provisional — финал при чартах */
    /* --radius НЕ переопределяем — остаётся 0.625rem (см. Task 2) */
    --sidebar: #ECEAF4;
    --sidebar-foreground: #17131F;
    --sidebar-primary: #754AE8;
    --sidebar-primary-foreground: #FFFFFF;
    --sidebar-accent: #ECEAF4;
    --sidebar-accent-foreground: #17131F;
    --sidebar-border: #E4E1EE;
    --sidebar-ring: #754AE8;
    /* Shadows — light (soft); питают shadow-*-утилиты через @theme inline */
    --elevation-1: 0 1px 2px rgba(23, 19, 31, 0.06);
    --elevation-2: 0 6px 18px rgba(23, 19, 31, 0.10);
    --elevation-3: 0 18px 50px rgba(23, 19, 31, 0.14);
    --glow-violet: 0 0 0 1px rgba(117, 74, 232, 0.30), 0 8px 30px rgba(117, 74, 232, 0.20);
    --focus-ring: 0 0 0 3px rgba(117, 74, 232, 0.18);
}
```

> `:root` уже содержит `--radius: 0.625rem` из исходного файла — оставляем как есть, строку не трогаем (в отличие от плана до правок).

- [ ] **Step 2: Переписать `.dark` (тёмная тема)**

В `frontend/src/index.css` заменить содержимое блока `.dark`. Включает тёмные (strong) значения сырых теней `--elevation-*`/`--glow-violet`/`--focus-ring` — те же имена, что в `:root`, поэтому `shadow-*`-утилиты переключаются по теме:

```css
.dark {
    --background: #0A0814;
    --foreground: #F4F2FA;
    --card: #16121F;
    --card-foreground: #F4F2FA;
    --popover: #1E1930;
    --popover-foreground: #F4F2FA;
    --primary: #754AE8;
    --primary-foreground: #FFFFFF;
    --primary-hover: #8B66F0;              /* dark: акцент светлеет на hover */
    --secondary: #110D1C;
    --secondary-foreground: #F4F2FA;
    --muted: #110D1C;
    --muted-foreground: #B5B2C4;
    --accent: #1E1930;                     /* нейтральный ховер shadcn, НЕ бренд */
    --accent-foreground: #F4F2FA;
    --destructive: #E8657A;                /* мягкие danger: светлый хью на тёмном */
    --destructive-solid: #CF4157;          /* сплошная danger-кнопка (обе темы) */
    --destructive-foreground: #FFFFFF;
    --accent-subtle: rgba(117, 74, 232, 0.16);  /* подложка subtle-варианта (dark, плотнее) */
    --border: #2A2640;
    --border-strong: #3A3556;
    --input: #2A2640;
    --ring: #754AE8;
    --chart-1: #8B66F0;
    --chart-2: #82D6CC;
    --chart-3: #BD9375;
    --chart-4: #A99BD6;                    /* provisional — финал при чартах */
    --chart-5: #6E5BA8;                    /* provisional — финал при чартах */
    --sidebar: #110D1C;
    --sidebar-foreground: #F4F2FA;
    --sidebar-primary: #754AE8;
    --sidebar-primary-foreground: #FFFFFF;
    --sidebar-accent: #1E1930;
    --sidebar-accent-foreground: #F4F2FA;
    --sidebar-border: #2A2640;
    --sidebar-ring: #754AE8;
    /* Shadows — dark (strong); те же сырые vars, что и в :root */
    --elevation-1: 0 1px 2px rgba(0, 0, 0, 0.4);
    --elevation-2: 0 6px 18px rgba(0, 0, 0, 0.5);
    --elevation-3: 0 18px 50px rgba(0, 0, 0, 0.6);
    --glow-violet: 0 0 0 1px rgba(117, 74, 232, 0.5), 0 8px 30px rgba(117, 74, 232, 0.35);
    --focus-ring: 0 0 0 3px rgba(117, 74, 232, 0.2);
}
```

- [ ] **Step 3: Сборка (гейт)**

Run (из `frontend/`):
```bash
npm run build
```
Expected: сборка успешна.

- [ ] **Step 4: Визуальная проверка обеих тем**

Run (из `frontend/`): `npm run dev`, открыть http://localhost:5173, переключать тему клавишей `d`.
Expected:
- Светлая: фон лавандово-белый `#F4F2FA`, текст тёмный, кнопка `Button` — фиолетовая `#754AE8` с белым текстом.
- Тёмная: фон почти чёрный `#0A0814`, текст светлый, кнопка — тот же фиолет.
- Переключение мгновенное, без вспышки переходов (`disableTransitionOnChange`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): bridge токенов DS на переменные shadcn (светлая/тёмная)"
```

---

### Task 4: Реколор компонента `button` под тона DS

**Files:**
- Modify: `frontend/src/components/ui/button-variants.ts`
- Modify: `frontend/src/components/ui/button.test.tsx`

**Interfaces:**
- Consumes: bridge-vars `--primary-hover`, `--destructive-solid`, `--border-strong` (Task 3); утилиты `rounded-md` (Task 2).
- Produces: варианты `default|outline|secondary|ghost|subtle|destructive|link`; новый `subtle`. `button.tsx` не меняется (`variant` пробрасывается, `VariantProps` подхватит `subtle` автоматически).

- [ ] **Step 1: Обновить тесты (failing first)**

Заменить содержимое `frontend/src/components/ui/button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Button } from "@/components/ui/button"

describe("Button", () => {
  it("рендерит текст и слот-атрибут", () => {
    render(<Button>Сохранить</Button>)
    const btn = screen.getByRole("button", { name: "Сохранить" })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute("data-slot", "button")
  })

  it("контролы: радиус md и вес normal (DS)", () => {
    render(<Button>Ок</Button>)
    const btn = screen.getByRole("button", { name: "Ок" })
    expect(btn.className).toContain("rounded-md")
    expect(btn.className).toContain("font-normal")
  })

  it("subtle-вариант: фиолетовая подложка через --accent-subtle", () => {
    render(<Button variant="subtle">Тон</Button>)
    const btn = screen.getByRole("button", { name: "Тон" })
    expect(btn).toHaveAttribute("data-variant", "subtle")
    expect(btn.className).toContain("var(--accent-subtle)")
  })

  it("destructive-вариант: сплошная заливка danger", () => {
    render(<Button variant="destructive">Удалить</Button>)
    const btn = screen.getByRole("button", { name: "Удалить" })
    expect(btn.className).toContain("var(--destructive-solid)")
  })
})
```

- [ ] **Step 2: Прогнать тесты — убедиться, что падают**

Run (из `frontend/`):
```bash
npm run test -- button
```
Expected: FAIL — новые проверки не проходят (в базе `font-medium`/`rounded-lg`, нет варианта `subtle`, `destructive` пока «мягкий» без `var(--destructive-solid)`).

- [ ] **Step 3: Обновить `button-variants.ts`**

Заменить содержимое `frontend/src/components/ui/button-variants.ts`:

```ts
import { cva } from "class-variance-authority"

// Вынесено из button.tsx, чтобы модуль компонента экспортировал только компонент
// (требование react-refresh / Fast Refresh).
export const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding text-sm font-normal whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 dark:disabled:opacity-60 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-[var(--primary-hover)]",
        outline:
          "border-border-strong bg-transparent text-foreground hover:border-primary hover:text-[var(--primary-hover)] aria-expanded:border-primary aria-expanded:text-[var(--primary-hover)]",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-accent hover:text-accent-foreground aria-expanded:bg-accent aria-expanded:text-accent-foreground",
        subtle:
          "bg-[var(--accent-subtle)] text-[var(--primary-hover)] hover:bg-primary/20",
        destructive:
          "bg-[var(--destructive-solid)] text-white hover:bg-[color-mix(in_srgb,var(--destructive-solid)_92%,#000)] focus-visible:border-destructive focus-visible:ring-destructive/30",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)
```

Изменения относительно базы: `rounded-lg`→`rounded-md`; `font-medium`→`font-normal`; добавлен `dark:disabled:opacity-60`; `default` hover → `--primary-hover`; `outline` переписан под DS-secondary (border-strong + hover бренд, без `bg-accent`); добавлен `subtle`; `destructive` → сплошной `--destructive-solid` + белый текст; `ghost` hover переведён на нейтральный токен `accent`.

> Focus-ring на `destructive` пока фиолетовый (`--ring`) с добавленным `ring-destructive/30` на focus-visible — компромисс; отдельный ring-цвет — на полиш (см. спеку).

- [ ] **Step 4: Прогнать тесты — убедиться, что проходят**

Run (из `frontend/`):
```bash
npm run test -- button
```
Expected: PASS — все 4 проверки зелёные.

- [ ] **Step 5: Lint + typecheck (гейт)**

Run (из `frontend/`):
```bash
npm run lint && npm run typecheck && npm run build
```
Expected: без ошибок (новый вариант `subtle` типизируется через `VariantProps`, `button.tsx` менять не нужно).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/button-variants.ts frontend/src/components/ui/button.test.tsx
git commit -m "feat(ui): реколор button под тона DS (subtle, сплошной danger, радиус/вес)"
```

---

### Task 5: Мини-витрина в `App.tsx` для визуальной проверки тем

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `Button` (все варианты), утилиты бренд-цветов/поверхностей из Task 2/3.
- Produces: экран с кнопками всех тонов + swatch'ами поверхностей/бренда/статусов для глазной проверки светлой и тёмной тем.

- [ ] **Step 1: Заменить содержимое `frontend/src/App.tsx`**

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

export function App() {
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

export default App
```

- [ ] **Step 2: Lint + typecheck + build (гейт)**

Run (из `frontend/`):
```bash
npm run lint && npm run typecheck && npm run build
```
Expected: без ошибок.

- [ ] **Step 3: Визуальная проверка обеих тем**

Run (из `frontend/`): `npm run dev`, открыть http://localhost:5173, переключать `d`.
Expected:
- Все 7 тонов кнопок читаемы в обеих темах; `Primary` меняет оттенок на hover (light темнеет, dark светлеет); `Danger` — сплошной красный `#CF4157` с белым текстом в обеих темах, текст читаем; `Disabled` не выглядит «пропавшим» в тёмной (opacity-60).
- Swatch'и: `background`/`card` контрастируют между собой; `primary` — фирменный фиолет; бренд-цвета видны.
- Тень на `card + shadow`: в светлой — мягкая нейтральная, в тёмной — заметно глубже (проверка, что `shadow-elevation-*` переключается по теме через сырые `--elevation-*`).
- Заголовок — гарнитурой Grtsk Giga, текст — Suisse Intl.

- [ ] **Step 4: Полный прогон CI фронта**

Run (из `frontend/`):
```bash
npm run lint && npm run typecheck && npm run test && npm run build
```
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): витрина токенов и тонов кнопок для проверки тем"
```

---

## Self-Review

**1. Spec coverage:**
- §Файловая структура (fonts, styles/fonts.css, assets/fonts) → Task 1. ✓
- §1 Токены `@theme` (бренд-цвета, шрифты, типографика, тени, радиусы, `font-synthesis`) → Task 1 (шрифты) + Task 2 (остальное). ✓
- §2 Bridge (все переменные shadcn, `--accent` нейтральный, chart без дублей, sidebar, `--destructive-solid`, `--border-strong`, `--primary-hover`) → Task 3. ✓
- §3 Button (радиус md, вес normal, hover primary/outline, `subtle`, сплошной danger, disabled opacity-60 dark) → Task 4. ✓
- §4 Проверка (build + визуал обеих тем, обновление button.test) → гейты в каждом таске + Task 5 витрина. ✓
- Вне объёма (каталог, `data-theme`, tokens.json, удаление хендоффа, точные px-размеры) — не запланировано намеренно. ✓
- Открытый вопрос 3 (палитра чартов) — chart-4/5 помечены `provisional` в Task 3, финал отложен. ✓

**2. Placeholder scan:** плейсхолдеров нет; весь код приведён полностью. `provisional`-значения чартов — осознанное решение спеки, не заглушка (значения конкретные, различимые).

**3. Type consistency:** имена bridge-vars (`--primary-hover`, `--destructive-solid`, `--border-strong`, `--accent-subtle`) совпадают между Task 3 (определение) и Task 4 (использование). Сырые тени `--elevation-1|2|3`/`--glow-violet`/`--focus-ring`: `@theme inline` маппинг (Task 2) ↔ определение в `:root`/`.dark` (Task 3) ↔ утилита `shadow-elevation-2` в витрине (Task 5). `--color-border-strong: var(--border-strong)` (Task 2) ↔ `--border-strong` (Task 3). Вариант `subtle` в cva (Task 4) ↔ ассерт `data-variant="subtle"` + `var(--accent-subtle)` (тест Task 4). `text-caption`/`font-display`/`bg-violet-bright`/`bg-mint`/`bg-tan` (Task 5) определены в Task 2.

## Polish backlog (вне объёма foundation)

- **woff2.** Сейчас самохостим сырые `.otf`/`.ttf` — тяжелее и без сжатия. Прогнать через woff2 (обычно −40–60% веса) при полишинге прода.
- **FOUT / `size-adjust`.** `font-display: swap` без `size-adjust` — разные метрики Suisse/Inter дают сдвиг лейаута на первых кадрах. Добить `size-adjust` в `@font-face` (или `font-display: optional`).
- **Focus-ring на `destructive`** — отдельный ring-цвет вместо фиолетового `--ring`.
- **Каталог компонентов** — следующий срез: card + badge + table (несущие для матрицы/светофора).
- **Точные px-размеры кнопки** (DS `11×24`) и DS-реколор `disabled` (border-strong/fg-subtle) вместо `opacity`.
- **Категориальная палитра чартов** (`--chart-4/5` сейчас provisional) — финал с реальными сериями на дашборде проектов.
