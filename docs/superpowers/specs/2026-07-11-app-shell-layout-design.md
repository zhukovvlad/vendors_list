# Дизайн: App Shell (sidebar + navbar)

**Дата:** 2026-07-11
**Ветка:** `feat/app-shell-layout`
**Источник идеи:** перенести layout из соседнего проекта
[`zhukovvlad/tenders-react`](https://github.com/zhukovvlad/tenders-react)
(`src/components/layout/{Layout,AppSidebar,Navbar}.tsx`) в текущий фронт Vendors.

## Цель

Дать приложению постоянную оболочку: сворачиваемый боковой сайдбар с навигацией +
верхнюю панель (navbar) с переключателем темы и меню пользователя. Визуально и
структурно — как в tenders-react, но **адаптировано под стек Vendors** (не
буквальный порт).

## Принятые решения (из брейнсторминга)

1. **Адаптация, не порт 1:1.** tenders собран на `react-router-dom` + собственный
   `theme-provider` + боевой `useAuth`. Vendors — на **TanStack Router**, с уже
   существующим (более продвинутым) `ThemeProvider` и без подключённого к фронту
   auth. Переносим *структуру и вид* оболочки, переиспользуя инфраструктуру Vendors.
2. **Меню:** реальные роуты + заглушки будущих экранов (ТЗ §4-5).
3. **Navbar:** переключатель темы (через существующий `useTheme`) + **статичный
   плейсхолдер** меню пользователя (avatar; Profile/Settings/Logout не активны, пока
   нет боевого SSO/RBAC — CLAUDE.md §2).
4. **Заглушки:** видимы, но `disabled` + бейдж «скоро»; не кликаются.
5. **sonner Toaster:** добавляем сразу в оболочку (готовность под будущие мутации).

## Не-цели (YAGNI)

- Боевая интеграция auth/logout — отдельная задача (ТЗ §2).
- Реализация самих будущих экранов (Проекты/Издания/Вендоры/Импорт) — только пункты-заглушки.
- Второй `ThemeProvider` из tenders — НЕ тащим (в Vendors уже есть свой в `main.tsx`).
- `react-router-dom` — НЕ добавляем (роутер уже TanStack).

## Архитектура

Новый каталог `frontend/src/components/layout/`:

- **`AppShell.tsx`** — корневая оболочка. Дерево:
  `SidebarProvider → <div flex min-h-screen> [ AppSidebar | <main flex-1
  overflow-y-auto> [ AppNavbar + <div px-4><Outlet/></div> ] ] ] + Toaster`.
  `ThemeProvider` здесь **не** оборачиваем — он уже висит в `main.tsx` над
  `RouterProvider`. `<Outlet/>` и `SidebarProvider` — из `@tanstack/react-router`
  и `@/components/ui/sidebar` соответственно.
- **`AppSidebar.tsx`** — `<Sidebar collapsible="icon">` с шапкой (лого + «Vendors»),
  `SidebarSeparator`, и `SidebarContent` из групп меню (см. ниже). Ссылки — через
  TanStack `<Link>`.
- **`AppNavbar.tsx`** — `<nav>` с `SidebarTrigger` слева; справа — переключатель
  темы (dropdown Light/Dark/System через `useTheme` Vendors) и avatar-меню
  (`DropdownMenu` + `Avatar`, пункты статичны/disabled).

### Интеграция в роутер

В [`frontend/src/router.tsx`](../../../frontend/src/router.tsx) `rootRoute`
меняется:

```ts
// было
const rootRoute = createRootRoute({ component: () => <Outlet /> })
// стало
const rootRoute = createRootRoute({ component: AppShell })
```

`AppShell` сам рендерит `<Outlet/>`. Все три существующих роута (`/`, `/matrix`,
`/design-system`) получают оболочку без изменений в их определениях. Экспорт
`routeTree` не меняется — интеграционные тесты (`router.test.tsx`) продолжают
строить memory-router из того же дерева.

## Навигация

Ссылки — `<Link>` из `@tanstack/react-router` (не `react-router-dom`). Активный
пункт подсвечивается штатной подсветкой TanStack (`activeProps`/`activeOptions`;
для `/` — `activeOptions={{ exact: true }}`, чтобы не «горел» на всех путях).

Группы (`SidebarGroup` + `SidebarGroupLabel`):

| Группа       | Пункт                   | Роут              | Статус          |
|--------------|-------------------------|-------------------|-----------------|
| Обзор        | Обзор                   | `/`               | активен         |
| Обзор        | Матрица перечня         | `/matrix`         | активен         |
| Проекты      | Проекты                 | — (§4)            | disabled «скоро»|
| Каталог      | Издания                 | — (§5)            | disabled «скоро»|
| Каталог      | Вендоры и соглашения    | — (§5)            | disabled «скоро»|
| Импорт       | Импорт Excel            | — (§5)            | disabled «скоро»|
| Разработка   | Дизайн-система          | `/design-system`  | активен         |

Заглушки: `SidebarMenuButton` с `disabled` (приглушённый вид) + маленький бейдж
«скоро» (DS `badge`). Не оборачиваются в `<Link>` — некуда вести.

Данные меню — декларативный массив групп в `AppSidebar.tsx` (иконки `lucide-react`,
уже в зависимостях). Активные пункты несут `to`, заглушки — `disabled: true`.

## Новые компоненты (shadcn, на токенах)

Добавляются в `frontend/src/components/ui/` через `npx shadcn add`:

- `sidebar` (+ транзитивные `sheet`, `tooltip`, `separator` — если ещё не стоят)
- `dropdown-menu`
- `avatar`
- `sonner`

Зависимость `sonner` добавляется в `frontend/package.json`.

**Токены — уже готовы.** `--sidebar-*` (light+dark) и их `@theme`-маппинг
`--color-sidebar-*` уже определены в
[`frontend/src/index.css`](../../../frontend/src/index.css) (строки 13-20, 112-119,
158-165) из интеграции дизайн-системы. Сайдбар красится темами из коробки —
дополнительных токенов заводить не нужно, только свериться после `shadcn add`.

**react-refresh lint.** `sidebar.tsx` экспортирует хук `useSidebar` и cva-варианты
вместе с компонентами → правило `react-refresh/only-export-components` заругается.
Решение — шапка `/* eslint-disable react-refresh/only-export-components */` в
сгенерированном файле (ровно как уже сделано в
[`theme-provider.tsx`](../../../frontend/src/components/theme-provider.tsx)). То же —
для любого другого ui-файла shadcn, где хук/варианты соседствуют с компонентами.

**Стиль shadcn CLI.** После `shadcn add` пройтись `prettier --write` по новым
файлам (CI гоняет `prettier --check`).

## Docstrings

По правилам CLAUDE.md (§Документирование):
- `AppShell.tsx`, `AppSidebar.tsx`, `AppNavbar.tsx` — модульный docstring (JSDoc
  `/** */`): за что отвечает + ключевой инвариант/ловушка (напр.: «ThemeProvider
  здесь НЕ оборачиваем — он в main.tsx»).
- Нетривиальные детали (подсветка `/` через `exact`, статичность меню юзера) —
  короткий комментарий по месту.

## Тесты (vitest, рядом с кодом)

`frontend/src/components/layout/AppShell.test.tsx` (memory-router из `routeTree`,
как в `router.test.tsx`):

1. Реальные пункты навигации отрендерены и ведут по правильным `href`
   (Обзор→`/`, Матрица→`/matrix`, Дизайн-система→`/design-system`).
2. Пункты-заглушки присутствуют, помечены «скоро» и `disabled` (нет `href`).
3. Navbar содержит переключатель темы; клик по «Dark»/«Light» вызывает смену темы
   (класс на `documentElement` меняется).
4. `SidebarTrigger` присутствует (сворачивание сайдбара доступно).

MSW-хендлеры для дашборд/матрица-запросов дочерних экранов не нужны, если тест
монтирует оболочку на маршруте без сетевых загрузчиков (напр. `/design-system`) или
мокает минимально — тест проверяет оболочку, не контент экранов.

## Проверки перед PR

- Ветка `feat/app-shell-layout` от `main`.
- Финал — локальный `just ci` (types не требуется — OpenAPI не трогаем; но ci
  включает prettier/eslint/tsc/vitest — всё должно быть зелёным).
- PR в `main`, `main` держим зелёным.

## Файлы (сводка изменений)

**Новые:**
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/components/layout/AppNavbar.tsx`
- `frontend/src/components/layout/AppShell.test.tsx`
- `frontend/src/components/ui/{sidebar,dropdown-menu,avatar,sonner,sheet,tooltip,separator}.tsx`
  (набор транзитивных — по факту `shadcn add`)

**Изменяемые:**
- `frontend/src/router.tsx` — `rootRoute.component = AppShell`
- `frontend/package.json` / lock — `sonner` и прочие радикс-зависимости shadcn
