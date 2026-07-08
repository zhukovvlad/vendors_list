# 2026-07-09 — Интеграция MR Design System (foundation)

Ветка `feat/design-system-integration` → PR [#3](https://github.com/zhukovvlad/vendors_list/pull/3).
Реализовано по методике subagent-driven-development (план
[docs/superpowers/plans/2026-07-09-design-system-integration.md](../superpowers/plans/2026-07-09-design-system-integration.md),
спека [.../specs/2026-07-08-design-system-integration-design.md](../superpowers/specs/2026-07-08-design-system-integration-design.md)):
5 задач, свежий субагент-исполнитель на каждую + отдельный ревьюер (spec + quality),
в конце — ревью всей ветки. Модели: оркестратор/ревьюеры — Opus, исполнители — Haiku/Sonnet.

Объём — **только фундамент**: токены, темы, шрифты, реколор `button`. Каталог
компонентов (card/badge/table/…) — следующий срез, сознательно вне объёма.

## Что сделано

**Подход Bridge.** DS-экстра (бренд-цвета, типографика, тени, радиусы) — в
`@theme` Tailwind v4; семантику переопределяем на **переменных shadcn**
(`--background`, `--primary`, `--card`, `--border`, `--ring`, `--destructive`,
`--chart-*`, `--sidebar-*`) в `:root` (светлая) и `.dark` (тёмная). Весь shadcn
перекрашивается автоматически; `theme-provider.tsx` и класс `.dark` не тронуты;
`data-theme` не вводили. Всё в [frontend/src/index.css](../../frontend/src/index.css).

- **Шрифты** ([styles/fonts.css](../../frontend/src/styles/fonts.css),
  [assets/fonts/](../../frontend/src/assets/fonts/)): самохостинг 5 файлов —
  Grtsk Giga (100/300/500) + Suisse Intl (300/400) через `@font-face`.
  `--font-sans` = Suisse→Inter-fallback, `--font-display` = Grtsk. `font-synthesis:
  none` глобально. **UI-вес = 400** (Suisse Medium в хендоффе нет; акцентный вес —
  Grtsk на заголовках).
- **@theme токены:** бренд-цвета (`--color-violet`/`-bright`/`-deep`, `mint`, `tan`,
  `lavender`), шкала типографики (`--text-display…caption` с line-height/tracking),
  маппинги теней (`--shadow-elevation-1|2|3`/`glow-violet`/`focus-ring`).
  Радиусы — **фиксированная лесенка** DS (`sm/md/lg/xl` = 2/4/8/10px); `--radius`
  не трогаем (влияет только на неиспользуемые 2xl/3xl/4xl — дрейфа нет).
- **Bridge `:root`/`.dark`:** вся палитра в hex DS. Новые bridge-vars —
  `--primary-hover` (light темнеет / dark светлеет), `--destructive-solid`,
  `--destructive-foreground`, `--border-strong`, `--accent-subtle`; сырые тени
  `--elevation-*`/`--glow-violet`/`--focus-ring` (тема-split, питают `shadow-*`).
- **Button** ([button-variants.ts](../../frontend/src/components/ui/button-variants.ts)):
  реколор под тона DS — радиус `md`, вес `normal`, hover primary/outline через
  `--primary-hover`, новый вариант `subtle` (фиолетовая подложка), сплошной
  `destructive` (`#CF4157` + белый), `disabled` в тёмной поднят до `opacity-60`.
  `button.tsx` не менялся (`subtle` подхватывается через `VariantProps`).
- **Витрина** ([App.tsx](../../frontend/src/App.tsx)): все 7 тонов кнопок + swatch'и
  поверхностей/бренда — для глазной проверки обеих тем.

## Верификация (выполнена)

- Полный фронт-гейт зелёный: `lint` + `prettier --check` + `typecheck` + vitest
  **5 passed** + `build` (5 шрифтов с хешем в `dist/`).
- CI на PR #3 — оба джоба зелёные (см. нюанс про prettier ниже).
- **Визуал обеих тем подтверждён** (скриншоты пользователя): светлая `#F4F2FA` /
  тёмная `#0A0814`, primary-фиолет `#754AE8`, сплошной Danger `#CF4157` + белый,
  `disabled` читаем в тёмной, тень карточки глубже в тёмной, заголовок Grtsk Giga /
  текст Suisse Intl.

## Решения и нюансы (важно для будущих сессий)

- **Bridge, не `data-theme`.** Раскладку тем хендоффа инвертировали (light → `:root`,
  dark → `.dark`), чтобы не трогать `theme-provider` и не заводить второй механизм
  темы. Реколор через переменные shadcn ⇒ будущие компоненты перекрашиваются бесплатно.
- **`--accent` = нейтральный**, не бренд. В shadcn это фон ховера почти всего
  интерактива (dropdown/select/ghost-hover) — фиолет тут сделал бы все меню
  брендовыми. Фиолетовая подложка отдана эксклюзивно варианту `subtle` через
  `--accent-subtle`.
- **Сплошной danger — единая заливка `#CF4157` в обеих темах** + белый текст
  (≈4.6:1, проходит AA). Тема-split `--destructive` (`#CF4157`/`#E8657A`) оставлен
  для мягких использований (текст/бордер/бейдж), где на тёмном нужен светлый хью.
- **`--destructive-foreground`** определён, но пока без `@theme inline`-маппинга и
  потребителя (danger-кнопка использует литерал `text-white`) — форвардный токен,
  занесён в [TECH_DEBT.md](../TECH_DEBT.md).
- **prettier ловится только полным `just ci`.** CI на PR упал на `Format check`:
  verbatim-код плана не был prettier-чистым (JSX > printWidth 80 в `App.tsx`;
  `dark:disabled:opacity-60` вне класс-ордера tailwind-плагина). Гейт исполнителей
  гонял `npm run lint/typecheck/test/build` — без `prettier --check`. Тот же класс
  промаха, что в [test-system](2026-07-08-test-system.md) (гоняли pytest, не ruff).
  **Зафиксировано правилом:** перед пушем — `just ci` (CLAUDE §7, DEVELOPMENT §Проверки).

## Что осталось / открытые хвосты

- **Каталог компонентов** — следующий срез (отдельный PR): `card` + `badge` +
  `table`, несущие для матрицы соответствия/светофора. Настоящие болячки реколора
  (ховеры меню, бейджи-статусы, заголовки таблиц) вылезут только на них.
- **Полиш** (в [TECH_DEBT.md](../TECH_DEBT.md)): woff2, `size-adjust`/FOUT,
  отдельный focus-ring на destructive, `--chart-4/5` (provisional), точные
  px-размеры кнопки, DS-реколор `disabled`, маппинг `--destructive-foreground`.
- Hover-сдвиг primary на статичных скринах не проверить — визуально курсором ок.
