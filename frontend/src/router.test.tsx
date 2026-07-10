import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createRouter,
  createMemoryHistory,
} from "@tanstack/react-router"
import { describe, expect, it } from "vitest"

import { routeTree } from "./router"

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>
  )
}

describe("routing", () => {
  it("/ рендерит дашборд «Обзор»", async () => {
    renderAt("/")
    await waitFor(() => expect(screen.getByText("Обзор")).toBeInTheDocument())
  })

  it("/matrix рендерит экран матрицы (фильтр «Тип объекта»)", async () => {
    renderAt("/matrix")
    await waitFor(() =>
      expect(screen.getByText("Тип объекта")).toBeInTheDocument()
    )
  })
})
