import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createRouter,
  createMemoryHistory,
} from "@tanstack/react-router"
import { describe, expect, it } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"

import { routeTree } from "./router"

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

describe("routing", () => {
  it("/ рендерит дашборд «Обзор»", async () => {
    renderAt("/")
    // «Обзор» — и заголовок экрана, и пункт навигации сайдбара (Task 4):
    // скоупим на h1, чтобы не словить неоднозначность по тексту.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 1, name: "Обзор" })
      ).toBeInTheDocument()
    )
  })

  it("/matrix рендерит экран матрицы (фильтр «Тип объекта»)", async () => {
    renderAt("/matrix")
    await waitFor(() =>
      expect(screen.getByText("Тип объекта")).toBeInTheDocument()
    )
  })

  it("/vendors рендерит заглушку раздела «в разработке»", async () => {
    renderAt("/vendors")
    await waitFor(() =>
      expect(screen.getByText("Раздел в разработке.")).toBeInTheDocument()
    )
  })
})
