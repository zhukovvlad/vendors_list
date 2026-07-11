import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { routeTree } from "@/router"
import { server } from "@/test/msw/server"
import { vendorFixture } from "@/test/msw/handlers"

function renderAt(path = "/vendors/5") {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>
  )
}

describe("VendorCardScreen — шапка", () => {
  it("рисует имя, локализованный тип, пилюлю соглашения и статус бренда", async () => {
    renderAt()
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("System Air")
    expect(screen.getByText("производитель")).toBeInTheDocument()
    expect(screen.getByText("соглашение")).toBeInTheDocument()
    expect(screen.getByText("самостоятельный бренд")).toBeInTheDocument()
  })

  it("показывает alias'ы", async () => {
    renderAt()
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument()
    expect(screen.getByText("SystemAir")).toBeInTheDocument()
  })

  it("скрывает заметку, когда она пустая", async () => {
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, note: null })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1 })
    expect(screen.queryByTestId("vendor-note")).not.toBeInTheDocument()
  })

  it("пилюля соглашения скрыта при starred=false", async () => {
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, starred: false })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1 })
    expect(screen.queryByText("соглашение")).not.toBeInTheDocument()
  })
})

describe("VendorCardScreen — Где разрешён", () => {
  it("раскрывает стандарт, показывает allowed-чип и зачёркнутый excluded с тултипом", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByText("Жилой дом"))
    expect(await screen.findByText("Делюкс")).toBeInTheDocument()
    const excluded = screen.getByText("Бизнес")
    // тултип/aria исключённого чипа несёт label релиза
    expect(excluded).toHaveAttribute(
      "aria-label",
      "Был в релизе «ред. 25.03.2026», исключён в текущем черновике"
    )
  })

  it("свёрнутый стандарт показывает счётчик позиций", async () => {
    renderAt()
    expect(await screen.findByText("1 позиций")).toBeInTheDocument()
  })
})
