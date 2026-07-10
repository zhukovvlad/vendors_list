# App Shell (сайдбар + тонкая шапка) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать приложению постоянную оболочку — сворачиваемый сайдбар с навигацией фазы 1 и пользовательским футером + тонкую шапку контента с хлебной крошкой.

**Architecture:** `SidebarProvider → [ AppSidebar | SidebarInset[ AppHeader + <Outlet/> ] ] + Toaster`. Оболочка встраивается в TanStack Router как `rootRoute.component`, поэтому все существующие роуты автоматически получают её. Тема и меню пользователя — в футере сайдбара; сверху только `SidebarTrigger` + крошка. Навигация/крошка — из активного роута через `useRouterState`.

**Tech Stack:** React 19, TanStack Router, shadcn/ui (style `radix-nova`, unified `radix-ui`), Tailwind v4 (токены в `src/index.css`), `sonner`, vitest + Testing Library.

**Спека:** [docs/superpowers/specs/2026-07-11-app-shell-layout-design.md](../specs/2026-07-11-app-shell-layout-design.md)

## Global Constraints

- **UI только на русском.** Лого — «Вендор-листы». Ярлык раздела матрицы — ровно «Каталог стандартов».
- **В навигации НЕТ пунктов** «Проекты», «Импорт Excel», «Матрица перечня». Матрица — стартовый экран раздела «Каталог стандартов» (`/matrix`), не отдельный пункт.
- **Ссылки — `<Link>` из `@tanstack/react-router`**, не `react-router-dom` (последний не добавлять).
- **`ThemeProvider` НЕ дублировать** — он уже в `frontend/src/main.tsx` над `RouterProvider`. Тему читать через `useTheme` из `@/components/theme-provider`.
- **DS на токенах** — цвета только через переменные (`bg-sidebar-primary`, `text-muted-foreground` и т.п.), без хардкода hex. Токены `--sidebar-*` уже есть в `src/index.css`.
- **react-refresh lint:** в ui-файлах shadcn, где хук/cva-варианты соседствуют с компонентами (`sidebar.tsx`), первая строка — `/* eslint-disable react-refresh/only-export-components */`.
- **Юзер-блок — плейсхолдер** (имя/роль/инициалы захардкожены) до боевого SSO/RBAC (ТЗ §2); пункты Профиль/Настройки/Выход неактивны.
- **Ветка** `feat/app-shell-layout` (уже создана) → PR в `main`. **Гейт каждого таска — `just ci` зелёный** (`main` держим зелёным).
- **`just types` не обязателен по смыслу** (OpenAPI не трогаем), но входит в `just ci` — прогоняется как есть.

---

## Файловая структура

**Новые:**
- `frontend/src/lib/env.ts` — `isDevBuild()`: обёртка над `import.meta.env.DEV` (мокабельна в тестах).
- `frontend/src/components/layout/breadcrumb-map.ts` — чистая функция `sectionLabelForPath`.
- `frontend/src/components/layout/breadcrumb-map.test.ts` — юнит-тест маппинга.
- `frontend/src/components/layout/AppShell.tsx` — корневая оболочка.
- `frontend/src/components/layout/AppSidebar.tsx` — сайдбар (навигация + футер).
- `frontend/src/components/layout/AppHeader.tsx` — тонкая шапка + крошка.
- `frontend/src/components/layout/ThemeControl.tsx` — контрол темы в футере.
- `frontend/src/components/layout/UserMenu.tsx` — блок юзера в футере (плейсхолдер).
- `frontend/src/components/layout/AppShell.test.tsx` — интеграционные тесты оболочки.
- `frontend/src/screens/vendors/VendorsScreen.tsx` — экран-заглушка «в разработке».
- `frontend/src/components/ui/{sidebar,dropdown-menu,avatar,breadcrumb,sonner,sheet,tooltip,separator}.tsx` — генерируются `shadcn add`.

**Изменяемые:**
- `frontend/src/router.tsx` — `rootRoute.component = AppShell`; новый роут `/vendors`.
- `frontend/package.json` / lock — зависимость `sonner` (+ радикс-зависимости shadcn).

---

## Task 1: Установка shadcn-примитивов + патч sonner

**Files:**
- Create: `frontend/src/components/ui/{sidebar,dropdown-menu,avatar,breadcrumb,sonner,sheet,tooltip,separator}.tsx` (через CLI)
- Modify: `frontend/src/components/ui/sonner.tsx` (патч импорта темы), `frontend/src/components/ui/sidebar.tsx` (eslint-disable)

**Interfaces:**
- Produces: ui-компоненты `Sidebar, SidebarProvider, SidebarInset, SidebarTrigger, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarSeparator` (из `@/components/ui/sidebar`); `DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator` (`@/components/ui/dropdown-menu`); `Avatar, AvatarFallback` (`@/components/ui/avatar`); `Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbPage` (`@/components/ui/breadcrumb`); `Toaster` (`@/components/ui/sonner`).

- [ ] **Step 1: Установить компоненты через shadcn CLI**

Run (из `frontend/`):
```bash
cd frontend && npx --yes shadcn@latest add sidebar dropdown-menu avatar breadcrumb sonner
```
Ожидаемо: созданы файлы в `src/components/ui/` (в т.ч. транзитивные `sheet.tsx`, `tooltip.tsx`, `separator.tsx`). В `package.json` добавлена `sonner`.

**Важно:** `skeleton.tsx` уже существует и кастомизирован (есть `skeleton.test.tsx`) —
**НЕ перезаписывать** (не передавать `--overwrite`; если CLI спросит про существующий
файл — оставить проектную версию). После установки убедиться, что `skeleton.test.tsx`
не сломан (прогон в Step 5).

- [ ] **Step 2: Пропатчить `sonner.tsx` под ThemeProvider Vendors**

shadcn генерирует `sonner.tsx` с импортом `useTheme` из `next-themes` (в проекте НЕ установлен — сломает сборку). Заменить на локальный провайдер. Итоговый файл:

```tsx
import { useTheme } from "@/components/theme-provider"
import { Toaster as Sonner, type ToasterProps } from "sonner"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      {...props}
    />
  )
}

export { Toaster }
```

- [ ] **Step 3: eslint-disable в `sidebar.tsx`**

Первой строкой файла `frontend/src/components/ui/sidebar.tsx` добавить:
```tsx
/* eslint-disable react-refresh/only-export-components */
```
(файл экспортирует хук `useSidebar` и cva-варианты рядом с компонентами — иначе `npm run lint` упадёт).

- [ ] **Step 4: Форматирование**

Run:
```bash
cd frontend && npm run format
```

- [ ] **Step 5: Сверка токенов и гейт**

Убедиться, что `src/index.css` содержит `--sidebar-*` (light+dark) и `--color-sidebar-*` в `@theme` (должны быть на месте, строки ~13-20, 112-119, 158-165 — новых токенов не добавляем).

Run:
```bash
cd frontend && npm run lint && npm run typecheck
```
Expected: обе команды PASS (0 ошибок).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui frontend/package.json frontend/package-lock.json
git commit -m "feat(ui): shadcn-примитивы для app shell (sidebar/dropdown/avatar/breadcrumb/sonner)"
```

---

## Task 2: Хлебная крошка — маппинг роут→метка (чистая функция, TDD)

**Files:**
- Create: `frontend/src/components/layout/breadcrumb-map.ts`
- Test: `frontend/src/components/layout/breadcrumb-map.test.ts`

**Interfaces:**
- Produces: `sectionLabelForPath(pathname: string): string` — метка раздела для крошки; неизвестный путь → `""`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/components/layout/breadcrumb-map.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { sectionLabelForPath } from "./breadcrumb-map"

describe("sectionLabelForPath", () => {
  it("маппит известные разделы фазы 1", () => {
    expect(sectionLabelForPath("/")).toBe("Обзор")
    expect(sectionLabelForPath("/matrix")).toBe("Каталог стандартов")
    expect(sectionLabelForPath("/vendors")).toBe("Вендоры")
    expect(sectionLabelForPath("/design-system")).toBe("Дизайн-система")
  })

  it("неизвестный путь → пустая метка", () => {
    expect(sectionLabelForPath("/nope")).toBe("")
  })
})
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run:
```bash
cd frontend && npx vitest run src/components/layout/breadcrumb-map.test.ts
```
Expected: FAIL — `Failed to resolve import "./breadcrumb-map"`.

- [ ] **Step 3: Реализовать маппинг**

`frontend/src/components/layout/breadcrumb-map.ts`:
```ts
/**
 * Метка раздела для хлебной крошки по pathname активного роута.
 *
 * Чистая функция — задел под глубокие уровни каталога (тип объекта, издание):
 * дополнительные крошки допишутся здесь без правок в шапке.
 */
const SECTION_LABELS: Record<string, string> = {
  "/": "Обзор",
  "/matrix": "Каталог стандартов",
  "/vendors": "Вендоры",
  "/design-system": "Дизайн-система",
}

export function sectionLabelForPath(pathname: string): string {
  return SECTION_LABELS[pathname] ?? ""
}
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run:
```bash
cd frontend && npx vitest run src/components/layout/breadcrumb-map.test.ts
```
Expected: PASS (2 теста).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/breadcrumb-map.ts frontend/src/components/layout/breadcrumb-map.test.ts
git commit -m "feat(layout): маппинг роут→метка для хлебной крошки"
```

---

## Task 3: Экран-заглушка «Вендоры» + роут `/vendors` (TDD)

**Files:**
- Create: `frontend/src/screens/vendors/VendorsScreen.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/router.test.tsx` (добавить кейс)

**Interfaces:**
- Consumes: `routeTree` из `@/router`.
- Produces: экспорт `VendorsScreen`; роут `/vendors` в `routeTree`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `frontend/src/router.test.tsx` внутри `describe("routing", …)`:
```tsx
  it("/vendors рендерит заглушку раздела «в разработке»", async () => {
    renderAt("/vendors")
    await waitFor(() =>
      expect(screen.getByText("Раздел в разработке.")).toBeInTheDocument()
    )
  })
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run:
```bash
cd frontend && npx vitest run src/router.test.tsx
```
Expected: FAIL — роут `/vendors` не найден (рендерится notFound / нет текста).

- [ ] **Step 3: Создать экран-заглушку**

`frontend/src/screens/vendors/VendorsScreen.tsx`:
```tsx
/**
 * Раздел «Вендоры» — активный раздел фазы 1; экран ещё не собран.
 * Заглушка-заполнитель до реализации (ТЗ §4).
 */
export function VendorsScreen() {
  return (
    <div className="py-16 text-center">
      <div className="text-h3 font-medium">Вендоры</div>
      <p className="mt-2 text-small text-muted-foreground">
        Раздел в разработке.
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Зарегистрировать роут**

В `frontend/src/router.tsx`:

Добавить импорт (рядом с остальными импортами экранов):
```tsx
import { VendorsScreen } from "@/screens/vendors/VendorsScreen"
```

Добавить определение роута (после `designSystemRoute`):
```tsx
const vendorsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/vendors",
  component: VendorsScreen,
})
```

Включить в дерево:
```tsx
export const routeTree = rootRoute.addChildren([
  dashboardRoute,
  matrixRoute,
  designSystemRoute,
  vendorsRoute,
])
```

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run:
```bash
cd frontend && npx vitest run src/router.test.tsx
```
Expected: PASS (3 теста).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/vendors/VendorsScreen.tsx frontend/src/router.tsx frontend/src/router.test.tsx
git commit -m "feat(vendors): экран-заглушка + роут /vendors"
```

---

## Task 4: Сборка оболочки (AppSidebar навигация + AppHeader + AppShell) + интеграция в роутер

**Files:**
- Create: `frontend/src/lib/env.ts`, `frontend/src/components/layout/{AppShell,AppSidebar,AppHeader}.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/components/layout/AppShell.test.tsx`

**Interfaces:**
- Consumes: `sectionLabelForPath` (Task 2); ui-примитивы (Task 1); `routeTree` (для теста).
- Produces: `AppShell` (React-компонент без пропсов, рендерит `<Outlet/>`); `isDevBuild(): boolean`. Футер сайдбара в этом таске содержит навигацию, Админку и dev-пункт; тема/юзер добавятся в Task 5.

- [ ] **Step 1: Обёртка dev-флага**

`frontend/src/lib/env.ts`:
```ts
/** Обёртка над import.meta.env.DEV — мокабельна в тестах (vi.mock). */
export function isDevBuild(): boolean {
  return import.meta.env.DEV
}
```

- [ ] **Step 2: Написать падающие тесты оболочки**

`frontend/src/components/layout/AppShell.test.tsx`:
```tsx
import { render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createRouter,
  createMemoryHistory,
} from "@tanstack/react-router"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { isDevBuild } from "@/lib/env"
import { routeTree } from "@/router"

vi.mock("@/lib/env", () => ({ isDevBuild: vi.fn(() => true) }))

beforeAll(() => {
  // shadcn Sidebar использует matchMedia (useIsMobile); в jsdom его нет.
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  }
  // Radix (DropdownMenu) в jsdom требует этих API — иначе меню не открывается.
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
})

afterEach(() => {
  vi.mocked(isDevBuild).mockReturnValue(true)
})

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <RouterProvider router={router as never} />
      </ThemeProvider>
    </QueryClientProvider>
  )
}

describe("AppShell — навигация", () => {
  it("рабочие пункты ведут по правильным роутам", () => {
    renderAt("/design-system")
    expect(screen.getByRole("link", { name: /Обзор/ })).toHaveAttribute(
      "href",
      "/"
    )
    expect(
      screen.getByRole("link", { name: /Каталог стандартов/ })
    ).toHaveAttribute("href", "/matrix")
    expect(screen.getByRole("link", { name: /Вендоры/ })).toHaveAttribute(
      "href",
      "/vendors"
    )
  })

  it("убранных разделов нет", () => {
    renderAt("/design-system")
    expect(screen.queryByText("Матрица перечня")).not.toBeInTheDocument()
    expect(screen.queryByText("Проекты")).not.toBeInTheDocument()
    expect(screen.queryByText(/Импорт/)).not.toBeInTheDocument()
  })

  it("Админка присутствует, помечена «в разработке» и не ссылка", () => {
    renderAt("/design-system")
    expect(screen.getByText("Админка")).toBeInTheDocument()
    expect(screen.getByText("в разработке")).toBeInTheDocument()
    expect(
      screen.queryByRole("link", { name: /Админка/ })
    ).not.toBeInTheDocument()
  })

  it("Дизайн-система видна в dev и скрыта вне dev", () => {
    vi.mocked(isDevBuild).mockReturnValue(true)
    renderAt("/design-system")
    expect(
      screen.getByRole("link", { name: /Дизайн-система/ })
    ).toBeInTheDocument()

    vi.mocked(isDevBuild).mockReturnValue(false)
    renderAt("/vendors")
    expect(
      screen.queryByRole("link", { name: /Дизайн-система/ })
    ).not.toBeInTheDocument()
  })
})

describe("AppShell — шапка", () => {
  it("крошка показывает метку активного раздела и есть триггер сайдбара", () => {
    renderAt("/vendors")
    // «Вендоры» встречается в навигации/заголовке экрана — скоупим на саму крошку
    // (shadcn Breadcrumb рендерит <nav aria-label="breadcrumb">).
    const crumb = screen.getByRole("navigation", { name: "breadcrumb" })
    expect(within(crumb).getByText("Вендоры")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Toggle Sidebar/i })
    ).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают**

Run:
```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: FAIL — нет `@/lib/env` / оболочка не смонтирована (rootRoute всё ещё голый Outlet).

- [ ] **Step 4: Создать `AppSidebar` (навигация + системный футер без темы/юзера)**

`frontend/src/components/layout/AppSidebar.tsx`:
```tsx
/**
 * Боковая навигация приложения (фаза 1).
 *
 * Содержит рабочие разделы + системный футер (Админка-заглушка и dev-витрина).
 * Контрол темы и блок пользователя добавляются в футер отдельно (ThemeControl,
 * UserMenu). Ссылки — TanStack <Link>; активность считаем из pathname.
 */
import { Link, useRouterState } from "@tanstack/react-router"
import { Building2, LayoutDashboard, Palette, Settings, Table2 } from "lucide-react"

import { isDevBuild } from "@/lib/env"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"

const NAV = [
  { title: "Обзор", to: "/", icon: LayoutDashboard, exact: true },
  { title: "Каталог стандартов", to: "/matrix", icon: Table2 },
  { title: "Вендоры", to: "/vendors", icon: Building2 },
] as const

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isActive = (to: string, exact?: boolean) =>
    exact ? pathname === to : pathname === to || pathname.startsWith(`${to}/`)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link to="/" className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-medium text-sidebar-primary-foreground">
            М
          </div>
          <span className="text-sm font-medium group-data-[collapsible=icon]:hidden">
            Вендор-листы
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.to, item.exact)}
                    tooltip={item.title}
                  >
                    <Link to={item.to}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarSeparator />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton disabled tooltip="Админка — в разработке">
              <Settings />
              <span>Админка</span>
              <span className="ml-auto text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                в разработке
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {isDevBuild() && (
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                isActive={isActive("/design-system")}
                tooltip="Дизайн-система"
              >
                <Link to="/design-system">
                  <Palette />
                  <span>Дизайн-система</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
```

> Иконки взяты из `lucide-react`; если в установленной версии имя отличается, подобрать ближайший существующий экспорт (проверка — `npm run typecheck`).

- [ ] **Step 5: Создать `AppHeader`**

`frontend/src/components/layout/AppHeader.tsx`:
```tsx
/** Тонкая шапка контента: триггер сворачивания сайдбара + хлебная крошка. */
import { useRouterState } from "@tanstack/react-router"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb"
import { SidebarTrigger } from "@/components/ui/sidebar"

import { sectionLabelForPath } from "./breadcrumb-map"

export function AppHeader() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const label = sectionLabelForPath(pathname)

  return (
    <header className="flex h-14 items-center gap-3 border-b px-4">
      <SidebarTrigger />
      {label && (
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>{label}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      )}
    </header>
  )
}
```

- [ ] **Step 6: Создать `AppShell`**

`frontend/src/components/layout/AppShell.tsx`:
```tsx
/**
 * Корневая оболочка приложения: сайдбар + тонкая шапка + область контента.
 *
 * ThemeProvider здесь НЕ оборачиваем — он уже в main.tsx над RouterProvider.
 * Встраивается как rootRoute.component, поэтому все роуты получают оболочку.
 */
import { Outlet } from "@tanstack/react-router"

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"

import { AppHeader } from "./AppHeader"
import { AppSidebar } from "./AppSidebar"

export function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <AppHeader />
        <div className="px-4 py-4">
          <Outlet />
        </div>
      </SidebarInset>
      <Toaster richColors position="bottom-right" />
    </SidebarProvider>
  )
}
```

- [ ] **Step 7: Встроить оболочку в роутер**

В `frontend/src/router.tsx`:

Добавить импорт:
```tsx
import { AppShell } from "@/components/layout/AppShell"
```

Заменить `rootRoute`:
```tsx
// было: const rootRoute = createRootRoute({ component: () => <Outlet /> })
const rootRoute = createRootRoute({ component: AppShell })
```
`Outlet` в импортах `router.tsx` может стать неиспользуемым — если `npm run lint` пожалуется, убрать `Outlet` из импорта `@tanstack/react-router`.

- [ ] **Step 8: Запустить тесты оболочки — убедиться, что проходят**

Run:
```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: PASS (5 тестов).

- [ ] **Step 9: Прогнать полный набор фронт-тестов (не сломали ли router.test)**

Run:
```bash
cd frontend && npm run test
```
Expected: PASS (в т.ч. `router.test.tsx` — оболочка не ломает существующие роуты).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/lib/env.ts frontend/src/components/layout frontend/src/router.tsx
git commit -m "feat(layout): app shell (сайдбар с навигацией + тонкая шапка) в роутере"
```

---

## Task 5: Футер сайдбара — контрол темы + плейсхолдер юзера + поведение при сворачивании (TDD)

**Files:**
- Create: `frontend/src/components/layout/{ThemeControl,UserMenu}.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx` (вставить футер-блоки), `frontend/src/components/layout/AppShell.test.tsx` (добавить кейсы)

**Interfaces:**
- Consumes: `useTheme` из `@/components/theme-provider`; ui-примитивы `dropdown-menu`, `avatar` (Task 1); `SidebarMenu*` (Task 1).
- Produces: `ThemeControl`, `UserMenu` (компоненты без пропсов для футера).

- [ ] **Step 1: Написать падающие тесты (тема + юзер + свёрнутый футер)**

Добавить в `frontend/src/components/layout/AppShell.test.tsx` новый блок (Radix-меню
открываем через `userEvent` — надёжнее `fireEvent` в jsdom):
```tsx
import userEvent from "@testing-library/user-event"

describe("AppShell — футер", () => {
  it("переключатель темы меняет класс на documentElement", async () => {
    const user = userEvent.setup()
    renderAt("/design-system")
    await user.click(screen.getByRole("button", { name: /тема/i }))
    await user.click(await screen.findByText("Тёмная"))
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("блок пользователя — плейсхолдер (имя и роль)", () => {
    renderAt("/design-system")
    expect(screen.getByText("Владимир Ж.")).toBeInTheDocument()
    expect(screen.getByText("Редактор")).toBeInTheDocument()
  })

  it("при сворачивании сайдбара футер (тема и юзер) не ломается", async () => {
    const user = userEvent.setup()
    renderAt("/design-system")
    await user.click(screen.getByRole("button", { name: /Toggle Sidebar/i }))
    // Триггеры темы и юзера остаются в DOM (доступны иконкой, не размонтированы).
    expect(screen.getByRole("button", { name: /тема/i })).toBeInTheDocument()
    expect(screen.getByText("Владимир Ж.")).toBeInTheDocument()
  })
})
```

> `import userEvent …` добавить в шапку файла (отдельной строкой к остальным импортам).

- [ ] **Step 2: Запустить — убедиться, что падают**

Run:
```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: FAIL — нет контрола темы/блока юзера в футере.

- [ ] **Step 3: Создать `ThemeControl`**

`frontend/src/components/layout/ThemeControl.tsx`:
```tsx
/**
 * Контрол темы в футере сайдбара. Переиспользует useTheme из ThemeProvider
 * (режим «Системная» и хоткей «d» уже живут там) — второй провайдер не заводим.
 */
import { Monitor, Moon, Sun } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function ThemeControl() {
  const { theme, setTheme } = useTheme()
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor
  const label =
    theme === "light"
      ? "Светлая тема"
      : theme === "dark"
        ? "Тёмная тема"
        : "Системная тема"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton tooltip={label} aria-label="Тема">
              <Icon />
              <span>{label}</span>
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end">
            <DropdownMenuItem onClick={() => setTheme("light")}>
              <Sun className="mr-2 h-4 w-4" />
              Светлая
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme("dark")}>
              <Moon className="mr-2 h-4 w-4" />
              Тёмная
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme("system")}>
              <Monitor className="mr-2 h-4 w-4" />
              Системная
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
```

> `aria-label="Тема"` даёт стабильное имя кнопки для теста (`name: /тема/i`) вне зависимости от текущего лейбла.

- [ ] **Step 4: Создать `UserMenu` (плейсхолдер)**

`frontend/src/components/layout/UserMenu.tsx`:
```tsx
/**
 * Блок пользователя в футере сайдбара.
 *
 * Имя/роль/инициалы — временный плейсхолдер до боевого SSO/RBAC (ТЗ §2);
 * пункты Профиль/Настройки/Выход неактивны.
 */
import { MoreVertical } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

// TODO(§2): заменить на данные из боевого SSO/RBAC.
const USER = { name: "Владимир Ж.", role: "Редактор", initials: "ВЖ" } as const

export function UserMenu() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" tooltip={USER.name}>
              <Avatar className="h-7 w-7">
                <AvatarFallback>{USER.initials}</AvatarFallback>
              </Avatar>
              <div className="flex flex-col text-left leading-tight group-data-[collapsible=icon]:hidden">
                <span className="text-sm">{USER.name}</span>
                <span className="text-xs text-muted-foreground">
                  {USER.role}
                </span>
              </div>
              <MoreVertical className="ml-auto h-4 w-4 group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end">
            <DropdownMenuLabel>{USER.name}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>Профиль</DropdownMenuItem>
            <DropdownMenuItem disabled>Настройки</DropdownMenuItem>
            <DropdownMenuItem disabled>Выход</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
```

- [ ] **Step 5: Вставить блоки в футер `AppSidebar`**

В `frontend/src/components/layout/AppSidebar.tsx`:

Добавить импорты:
```tsx
import { ThemeControl } from "./ThemeControl"
import { UserMenu } from "./UserMenu"
```

В `<SidebarFooter>`, после `</SidebarMenu>` (с Админкой/dev-пунктом) и перед `</SidebarFooter>`, добавить:
```tsx
        <ThemeControl />
        <UserMenu />
```

- [ ] **Step 6: Запустить тесты оболочки — убедиться, что проходят**

Run:
```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: PASS (8 тестов).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/layout/ThemeControl.tsx frontend/src/components/layout/UserMenu.tsx frontend/src/components/layout/AppSidebar.tsx frontend/src/components/layout/AppShell.test.tsx
git commit -m "feat(layout): футер сайдбара — контрол темы и плейсхолдер юзера"
```

---

## Task 6: Финальная проверка и ручной прогон

**Files:** — (только проверки)

- [ ] **Step 1: Полный CI-гейт**

Run (из корня репо):
```bash
just ci
```
Expected: PASS — `types`, `lint` (eslint + prettier --check), `typecheck` (mypy + tsc), `test` (pytest + vitest) все зелёные.

- [ ] **Step 2: Ручная проверка в браузере**

Run:
```bash
just dev-front
```
Открыть http://localhost:5173 и проверить:
- сайдбар: лого «Вендор-листы», пункты Обзор / Каталог стандартов / Вендоры; активный подсвечен;
- футер: Админка приглушена и не кликается; Дизайн-система видна (dev); контрол темы переключает светлую/тёмную/системную; блок юзера «Владимир Ж. · Редактор»;
- **свёрнутый сайдбар** (клик по триггеру): пункты и футер схлопываются в иконки, имя/роль/лейблы прячутся, тема и юзер доступны иконкой, вёрстка не едет;
- шапка: крошка меняется по разделам (Обзор → Каталог стандартов → Вендоры);
- светлая и тёмная темы обе выглядят корректно (токены `--sidebar-*`).

- [ ] **Step 3: Пуш ветки и PR**

```bash
git push -u origin feat/app-shell-layout
gh pr create --base main --title "feat: app shell (сайдбар + тонкая шапка)" --body "См. spec docs/superpowers/specs/2026-07-11-app-shell-layout-design.md"
```

- [ ] **Step 4: Девлог (после мержа)**

Завести `docs/devlog/2026-07-11-app-shell-layout.md` (хронология работ, файл на задачу) и при необходимости обновить CLAUDE.md (карта репозитория: `components/layout/`, новый роут `/vendors`, dev-only витрина).
