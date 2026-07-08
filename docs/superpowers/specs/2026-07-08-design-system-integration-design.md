# Дизайн: интеграция MR Design System во фронтенд (foundation)

**Дата:** 2026-07-08
**Ветка:** `feat/design-system-integration`
**Статус:** дизайн согласован, ждёт ревью спеки

## Цель

Внедрить фирменную дизайн-систему **MR Design System (v1.0)** в существующий
фронтенд, **сохранив shadcn/ui как основу** компонентов и обеспечив **две темы**
(светлую и тёмную). Объём — **только фундамент**: токены, темы, шрифты и реколор
существующего компонента `button`. Каталог компонентов (card/badge/table/tabs/
charts/inputs) собираем позже, под конкретные экраны (§3–4 ТЗ ещё TODO).

Источник правды по значениям — хендофф `temp/design_handoff_mr_design_system_v4/`
(hi-fi, hex-exact). Файлы `examples/` и `reference/` остаются в `temp/` как
справка и **в бандл не тянутся**.

## Контекст (исходное состояние)

- **Фронт:** Vite + React 19 + TS, **Tailwind v4** (CSS-first, `@theme inline`
  прямо в `frontend/src/index.css`), shadcn (`radix-nova`, baseColor `neutral`,
  `cssVariables: true`). Компонент пока один — `button`. Шрифт — Inter.
- **Темизация уже есть:** class-based `.dark`/`.light` на `<html>` через
  `frontend/src/components/theme-provider.tsx` (+ режим `system`, тумблер по
  клавише `d`, синхронизация между вкладками, `disableTransitionOnChange`).
  Дефолт — `system`.
- **Хендофф v4:** `tokens/tailwind.theme.css` — CSS-first `@theme`. Вводит
  **собственные** имена (`--color-accent`, `--color-bg-base`, `--font-display`…)
  и переключает тему через атрибут **`data-theme="light"`** (dark по умолчанию).

## Ключевое противоречие и решение

Хендофф и текущий проект расходятся в двух местах:

1. **Имена переменных.** Хендофф: `--color-*` / `--ds-*`. shadcn: `--background`,
   `--primary`, `--card`, `--border`, `--ring`, `--destructive`, `--chart-*`.
2. **Механизм темы.** Хендофф: атрибут `data-theme="light"`, dark по умолчанию.
   Проект: класс `.dark`, light по умолчанию, драйвер — `theme-provider`.

**Решение (подход A — Bridge):** экстра-токены DS кладём в `@theme`; **семантику
переопределяем на переменных shadcn** в `:root` (светлая) и `.dark` (тёмная).
Тогда весь shadcn перекрашивается автоматически, а `theme-provider` и класс
`.dark` не трогаем. Механизм `data-theme` **не вводим** (раскладку тем хендоффа
инвертируем: light → `:root`, dark → `.dark`).

Отвергнутые альтернативы:
- **B. Импорт v4-файла как есть** (`data-theme` + `--color-*`): shadcn-компоненты
  останутся серыми, два несогласованных механизма темы. Против золотого правила
  «shadcn как основа».
- **C. Гибрид** (оба набора переменных): дублирование и неоднозначность где что
  использовать. YAGNI.

## Решения (согласовано)

- **Объём:** только фундамент (токены + темы + шрифты + реколор `button`).
- **Шрифты:** самохостинг — коммитим `.otf/.ttf` в репо, добавляем `@font-face`.
  Права на веб-использование есть.
- **Тема по умолчанию:** оставляем `system` — `theme-provider` не меняем.

## Файловая структура

```
frontend/
├─ src/
│  ├─ index.css                 ← правим: @theme (DS-экстра) + bridge :root/.dark
│  ├─ styles/
│  │  └─ fonts.css              ← новый: @font-face (self-host)
│  └─ assets/fonts/             ← новый: 5 файлов Grtsk Giga + Suisse Intl
│     ├─ Grtsk-Giga-Thin.otf        (weight 100)
│     ├─ GrtskGiga-Light.ttf        (weight 300)
│     ├─ Grtsk-Giga-Medium.otf      (weight 500)
│     ├─ SuisseIntl-Light.otf       (weight 300)
│     └─ SuisseIntl-Regular.otf     (weight 400)
```

- Файлы шрифтов копируем из `temp/design_handoff_mr_design_system_v4/fonts/`.
- `src/styles/fonts.css` (`@font-face`) импортируется **первым** в `index.css`.
- `@fontsource-variable/inter` **оставляем** как fallback внутри `--font-sans`.

## Раздел 1 — Токены (`@theme`) в `index.css`

Переносим из `tokens/tailwind.theme.css` DS-примитивы и «экстру», **минус то,
что дублирует семантику shadcn** (её закрывает bridge, раздел 2):

- **Бренд-цвета:** `--color-violet` / `-bright` / `-deep`, `--color-mint`,
  `--color-tan`, `--color-lavender` → утилиты `bg-violet-bright`, `text-mint` и т.д.
- **Шрифты:** `--font-display: "Grtsk Giga", system-ui, sans-serif`;
  переопределяем `--font-sans: "Suisse Intl", "Inter Variable", system-ui, sans-serif`
  (текстовая гарнитура — основная), `--font-heading: var(--font-display)`.
- **Типографика:** `--text-display/h1/h2/h3/body-lg/body/small/caption` с парами
  `--line-height` и `--letter-spacing` (значения из хендоффа).
- **Тени:** `--shadow-elevation-1/2/3`, `--shadow-glow-violet`,
  `--shadow-focus-ring` → `shadow-glow-violet` и т.п.
- **Радиусы:** см. раздел 3 (заменяем calc-лесенку shadcn на фиксированную DS).
- **Spacing:** не трогаем — дефолт Tailwind v4 уже 4px-базовый и совпадает с DS.

Значения — hex из хендоффа (fidelity hex-exact), в oklch не перегоняем.

## Раздел 2 — Bridge: семантика shadcn (ядро реколора)

Переопределяем переменные shadcn DS-значениями. **Раскладка инвертирована
относительно хендоффа:** светлая в `:root`, тёмная в `.dark`.

| shadcn var | Light (`:root`) | Dark (`.dark`) | источник DS |
|---|---|---|---|
| `--background` | `#F4F2FA` | `#0A0814` | bg-base |
| `--foreground` | `#17131F` | `#F4F2FA` | fg |
| `--card` | `#FFFFFF` | `#16121F` | surface |
| `--card-foreground` | `#17131F` | `#F4F2FA` | fg |
| `--popover` | `#FFFFFF` | `#1E1930` | elevated |
| `--popover-foreground` | `#17131F` | `#F4F2FA` | fg |
| `--primary` | `#754AE8` | `#754AE8` | accent |
| `--primary-foreground` | `#FFFFFF` | `#FFFFFF` | white |
| `--secondary` | `#ECEAF4` | `#110D1C` | bg-sunken |
| `--secondary-foreground` | `#17131F` | `#F4F2FA` | fg |
| `--muted` | `#ECEAF4` | `#110D1C` | bg-sunken |
| `--muted-foreground` | `#56526B` | `#B5B2C4` | fg-muted |
| `--accent` (hover-фон shadcn) | `rgba(117,74,232,0.10)` | `rgba(117,74,232,0.16)` | violet-subtle |
| `--accent-foreground` | `#5E3AC8` | `#8B66F0` | accent-hover |
| `--border` | `#E4E1EE` | `#2A2640` | border |
| `--input` | `#E4E1EE` | `#2A2640` | border |
| `--ring` | `#754AE8` | `#754AE8` | accent |
| `--destructive` | `#CF4157` | `#E8657A` | danger-state |
| `--chart-1` | `#754AE8` | `#8B66F0` | violet / bright |
| `--chart-2` | `#158173` | `#82D6CC` | mint (light темнее) |
| `--chart-3` | `#9A6636` | `#BD9375` | tan (light темнее) |
| `--chart-4` | `#5E3AC8` | `#5733C0` | violet-deep |
| `--chart-5` | `#5029B0` | `#5733C0` | violet-active/deep |

Дополнительно:
- **`--sidebar-*`** переопределяем в тон (сайдбара пока нет, но чтобы не осталось
  серых дефолтов): `--sidebar` = sunken, `--sidebar-primary` = accent и т.д.
- **`--primary-hover`** — новый bridge-var для hover primary-кнопки (light
  `#5E3AC8` темнеет, dark `#8B66F0` светлеет). Нужен разделу 3.
- shadcn использует oklch с alpha (`bg-primary/80` и т.п.) — hex значения с
  `color-mix`/alpha-модификаторами Tailwind работают корректно.

## Раздел 3 — Button и радиусы (ПРЕДЛОЖЕНИЕ, к обсуждению с ревьюером)

> Этот раздел — предложение. Финальные решения по маппингу тонов, радиусам и
> глубине пиксель-перфекта принимаем на ревью спеки/кода. Ниже — отправная точка.

**Радиусы.** DS — фиксированная лесенка (`sm 2 / md 4 / lg 8 / xl 10`), контролы =
`md` 4px, карточки = `lg` 8px / `xl` 10px. shadcn выводит радиусы пропорционально
от `--radius` через `calc()`. Предложение: **заменить `@theme`-блок радиусов на
фиксированную лесенку DS** (`--radius-sm:2px; --radius-md:4px; --radius-lg:8px;
--radius-xl:10px`, без calc), базовый `--radius: 8px`.

**Button — маппинг тонов DS на варианты shadcn** (`button-variants.ts`):

| DS-тон | shadcn variant | предлагаемое изменение |
|---|---|---|
| primary | `default` | hover → `--primary-hover` (light темнеет, dark светлеет) |
| secondary (контурная) | `outline` | после реколора ≈ DS; hover → border/text accent |
| subtle | **новый `subtle`** | фон violet-subtle, текст accent-hover |
| ghost | `ghost` | без изменений (реколор автоматом) |
| danger (сплошная) | `destructive` | заменить «мягкий» стиль на сплошной `bg-destructive text-white` |
| link | `link` | без изменений |

- Радиус кнопки: `rounded-lg` → `rounded-md` (4px, контролы DS).
- **Осознанные отступления (foundation, не пиксель-перфект):**
  1. Размеры кнопки оставляем shadcn (`h-8/px-2.5`), не переводим в точные DS
     `11×24` — это полиш под экраны.
  2. `disabled` оставляем shadcn-механизм (`opacity-50`), а не DS-реколор
     (border-strong / fg-subtle).
  Оба легко довести позже.

## Раздел 4 — Проверка и границы

**Проверка (foundation):**
- `just ci` (фронт): lint, typecheck, `vite build`, vitest.
- `button.test.tsx` прогнать; при смене классов вариантов подправить ассерты.
- Глазами: `just dev-front`, тумблер `d` — светлая/тёмная переключаются, бренд-
  фиолет виден, шрифты Grtsk Giga / Suisse Intl подхватились.
- Мини-витрину в `App.tsx` обновить на несколько тонов кнопки + пару swatch'ей —
  только чтобы было на чём смотреть темы (опционально, легко откатить).

**Вне объёма (сознательно):**
- Каталог компонентов (card/badge/table/tabs/charts/inputs).
- Точные px-размеры компонентов (полиш).
- Механизм `data-theme` (используем класс `.dark`).
- Пайплайн `tokens.json` / Style Dictionary.
- Удаление хендоффа из `temp/`.

## Открытые вопросы для ревью

1. Маппинг тонов кнопки и решение по радиусам (раздел 3) — подтвердить/скорректировать.
2. Глубина пиксель-перфекта на этом этапе (оставляем ли отступления по размерам и disabled).
3. Точные значения `--chart-*` для светлой темы (читаемость бренд-hue на светлом фоне).
