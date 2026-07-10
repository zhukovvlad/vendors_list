import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "@/test/msw/server"
import { dashboardFixture } from "@/test/msw/handlers"

import { DashboardScreen } from "./DashboardScreen"

function renderScreen() {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <DashboardScreen />
    </QueryClientProvider>
  )
}

describe("DashboardScreen", () => {
  it("показывает три метрики с числами", async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText("412")).toBeInTheDocument())
    expect(screen.getByText("248")).toBeInTheDocument()
    expect(screen.getByText(/142/)).toBeInTheDocument()
  })

  it("список черновиков и залежавшийся в «Требует внимания»", async () => {
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText(/Жилой дом/)).toBeInTheDocument()
    )
    expect(screen.getAllByText(/Соцобъект/)).toHaveLength(2)
    expect(screen.getByText(/6 пар вендоров/)).toBeInTheDocument()
  })

  it("«всё чисто», когда внимания не требуется", async () => {
    server.use(
      http.get("/api/dashboard", () =>
        HttpResponse.json({
          summary: { ...dashboardFixture.summary, merge_candidate_pairs: 0 },
          drafts: [{ ...dashboardFixture.drafts[0], is_stale: false }],
        })
      )
    )
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText(/всё чисто/i)).toBeInTheDocument()
    )
  })

  it("скелетоны на время загрузки (до ответа)", () => {
    const { container } = (() => {
      const qc = new QueryClient()
      return render(
        <QueryClientProvider client={qc}>
          <DashboardScreen />
        </QueryClientProvider>
      )
    })()
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(
      0
    )
  })
})
