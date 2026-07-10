import { cleanup, render, screen, within } from "@testing-library/react"
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

// Роутер резолвит матчинг асинхронно даже без loader'ов (см. router.test.tsx —
// там та же асинхронность обходится через `await waitFor`). Здесь дожидаемся
// `router.load()` до рендера, чтобы сборка была видна сразу — без ослабления
// последующих синхронных assert'ов (`getByRole` и т.п.).
async function renderAt(path: string) {
  // Тест «Дизайн-система видна в dev и скрыта вне dev» зовёт renderAt дважды
  // подряд в одном it() (разные пути/мок isDevBuild) — без cleanup() предыдущий
  // рендер остаётся в DOM и даёт ложные "multiple elements".
  cleanup()
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  await router.load()
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
  it("рабочие пункты ведут по правильным роутам", async () => {
    await renderAt("/design-system")
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

  it("убранных разделов нет", async () => {
    await renderAt("/design-system")
    expect(screen.queryByText("Матрица перечня")).not.toBeInTheDocument()
    expect(screen.queryByText("Проекты")).not.toBeInTheDocument()
    expect(screen.queryByText(/Импорт/)).not.toBeInTheDocument()
  })

  it("Админка присутствует, помечена «в разработке» и не ссылка", async () => {
    await renderAt("/design-system")
    expect(screen.getByText("Админка")).toBeInTheDocument()
    expect(screen.getByText("в разработке")).toBeInTheDocument()
    expect(
      screen.queryByRole("link", { name: /Админка/ })
    ).not.toBeInTheDocument()
  })

  it("Дизайн-система видна в dev и скрыта вне dev", async () => {
    // На /design-system шапка тоже показывает крошку «Дизайн-система»
    // (shadcn BreadcrumbPage рендерит role="link" для текущей страницы) —
    // скоупим на футер сайдбара, чтобы не словить совпадение по имени с крошкой.
    vi.mocked(isDevBuild).mockReturnValue(true)
    await renderAt("/design-system")
    const sidebarFooter = document.querySelector(
      '[data-slot="sidebar-footer"]'
    ) as HTMLElement
    expect(
      within(sidebarFooter).getByRole("link", { name: /Дизайн-система/ })
    ).toBeInTheDocument()

    vi.mocked(isDevBuild).mockReturnValue(false)
    await renderAt("/vendors")
    expect(
      screen.queryByRole("link", { name: /Дизайн-система/ })
    ).not.toBeInTheDocument()
  })
})

describe("AppShell — шапка", () => {
  it("крошка показывает метку активного раздела и есть триггер сайдбара", async () => {
    await renderAt("/vendors")
    // «Вендоры» встречается в навигации/заголовке экрана — скоупим на саму крошку
    // (shadcn Breadcrumb рендерит <nav aria-label="breadcrumb">).
    const crumb = screen.getByRole("navigation", { name: "breadcrumb" })
    expect(within(crumb).getByText("Вендоры")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Свернуть меню/i })
    ).toBeInTheDocument()
  })
})
