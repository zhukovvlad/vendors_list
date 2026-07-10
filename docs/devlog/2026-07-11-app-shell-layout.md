# 2026-07-11 — App Shell (сайдбар + тонкая шапка)

Ветка `feat/app-shell-layout`. Реализовано по методике subagent-driven-development
(план [docs/superpowers/plans/2026-07-11-app-shell-layout.md](../superpowers/plans/2026-07-11-app-shell-layout.md),
спека [.../specs/2026-07-11-app-shell-layout-design.md](../superpowers/specs/2026-07-11-app-shell-layout-design.md)):
6 задач (failing-first в TDD-тасках), свежий субагент-исполнитель на задачу +
двухстадийное ревью между тасками, финальное whole-branch ревью (Opus) перед PR.

Цель — дать приложению постоянную **оболочку**: сворачиваемый боковой сайдбар с
навигацией фазы 1 и пользовательским футером + тонкая шапка контента с хлебной
крошкой. Все существующие роуты получают оболочку автоматически. Адаптация вида из
соседнего `tenders-react` под стек Vendors (TanStack Router, существующий
`ThemeProvider`), не буквальный порт.

## Что сделано

- **shadcn-примитивы** (`components/ui/`): `sidebar` (+ транзитивные `sheet`,
  `tooltip`, `separator`), `dropdown-menu`, `avatar`, `breadcrumb`, `sonner` через
  `shadcn add`. `sonner.tsx` пропатчен под локальный `useTheme` из
  `@/components/theme-provider` (shadcn генерит импорт из `next-themes` — в проекте
  нет, снёс мёртвую зависимость). `sidebar.tsx` — первой строкой
  `eslint-disable react-refresh/only-export-components`; все англ. accessibility-строки
  локализованы (RU-only): sr-only триггера «Свернуть меню», «Закрыть», «Ещё», мобильная
  «Боковая панель».
- **`AppShell` / `AppSidebar` / `AppHeader`** (`components/layout/`) —
  `SidebarProvider → AppSidebar | SidebarInset[ AppHeader + <Outlet/> ] + Toaster`.
  Встроена как `rootRoute.component = AppShell` в [router.tsx](../../frontend/src/router.tsx):
  оболочку получают все роуты, определения существующих роутов не менялись, экспорт
  `routeTree` сохранён (memory-router в тестах).
- **Навигация** (декларативный массив, иконки `lucide-react`): Обзор (`/`), Каталог
  стандартов (`/matrix`), Вендоры (`/vendors`) — ссылки `<Link>` TanStack, активность
  из `useRouterState` (для `/` — `exact`). Футер: Админка (`disabled`, «в разработке»,
  не ссылка), Дизайн-система (только в dev — `isDevBuild()` поверх `import.meta.env.DEV`),
  контрол темы, блок пользователя.
- **Хлебная крошка** — чистая функция `sectionLabelForPath(pathname)`
  ([breadcrumb-map.ts](../../frontend/src/components/layout/breadcrumb-map.ts), задел под
  глубокие уровни каталога), метка из активного роута. Шапка: `SidebarTrigger` + крошка.
- **Футер сайдбара**: `ThemeControl` (Светлая/Тёмная/Системная поверх существующего
  `useTheme` — второй провайдер НЕ заводим, хоткей «d» уже в `ThemeProvider`) и
  `UserMenu` (плейсхолдер «Владимир Ж. · Редактор», инициалы «ВЖ», пункты
  Профиль/Настройки/Выход `disabled` до боевого SSO/RBAC — TODO §2).
- **Экран-заглушка** `screens/vendors/VendorsScreen` («Раздел в разработке.») + роут
  `/vendors` (активный раздел фазы 1, экран ещё не собран).

## Ключевые решения

- **Оболочка через `rootRoute.component`** — единая точка, все роуты наследуют без
  правок. `Outlet` рендерит `AppShell`.
- **`ThemeProvider` не дублируется** — живёт в `main.tsx` над `RouterProvider`;
  оболочка и футер читают тему через `useTheme`. `sonner` Toaster тоже потребляет тему
  из него.
- **Дизайн-система — dev-only пункт**, роут `/design-system` остаётся (тесты/прямой
  заход). Админка — системный `disabled`-пункт без роута (экран — фаза 6).
- **Токены `--sidebar-*` уже были** в `index.css` (light+dark) — сайдбар красится
  темами из коробки, новых токенов не заводили, хардкода hex в layout-коде нет.
- **Юзер-блок — статичный плейсхолдер** до боевого auth (ТЗ §2).

## Ловушки (для будущих UI-задач на shadcn+Radix в jsdom)

- **`SidebarProvider` не оборачивал детей в `TooltipProvider`** (пропуск апстрим-shadcn) —
  любой `SidebarMenuButton` с `tooltip=` падал в error boundary. Это НЕ тест-артефакт,
  а реальный прод-краш; добавлен `<TooltipProvider delayDuration={0}>` в провайдер.
- **jsdom-полифилы централизованы в [`src/test/setup.ts`](../../frontend/src/test/setup.ts)**:
  `matchMedia` (useIsMobile сайдбара), `hasPointerCapture`/`scrollIntoView` (Radix
  DropdownMenu), `ResizeObserver` (Radix Popper-позиционирование меню). Порядок MSW
  сохранён — `server.listen()` остаётся синхронным на верхнем уровне после полифилов
  (openapi-fetch кеширует fetch на импорте), полифилы `fetch`/`Request` не трогают.
- **Коллизии по accessible name** после монтирования оболочки на каждом роуте: лейблы
  навигации совпадают с заголовками экранов/крошкой — ассерты в `router.test`/
  `MatrixScreen.test`/`AppShell.test` заскоуплены (`heading level 1`,
  `nav[aria-label=breadcrumb]`, `[data-slot=sidebar-footer]`), не ослаблены. Обоим
  пре-существующим тест-файлам добавлен `<ThemeProvider>` (Toaster теперь требует тему
  на каждом роуте).

## Проверки

- `just ci` зелёный: backend 127 passed, frontend 40 passed (14 файлов),
  ruff/mypy/tsc/prettier/eslint чисто.
- **Ручная проверка в реальном браузере** (headless Chromium через Playwright,
  smoke-скрипт): лого «Вендор-листы»; навигация ведёт по `/`,`/matrix`,`/vendors`;
  крошка меняется Обзор→Каталог стандартов→Вендоры; сворачивание сайдбара (иконки,
  лейблы прячутся, тема/юзер остаются доступны, лейаут не едет); контрол темы флипает
  `documentElement.dark`; светлая и тёмная обе корректны на токенах; **0 ошибок в
  консоли**.

## Отложено (см. TECH_DEBT)

- Дублирование набора лейблов разделов: `NAV` (`AppSidebar`) vs `SECTION_LABELS`
  (`breadcrumb-map`) — риск рассинхрона; сознательный компромисс (чистая функция —
  задел под глубокие крошки), свести при появлении вложенных уровней.
- Косметика: `aria-label` `SidebarRail` = «Свернуть меню» (для toggle точнее было бы
  «Переключить меню»; план мандатировал «Свернуть меню», тесты запрашивают по нему).
- jsdom-шум `Not implemented: window.scrollTo` в vitest (навигация роутера) — можно
  заглушить stub'ом в `setup.ts`, не блокер.
