import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { render, screen, waitFor } from "@testing-library/react"
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
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "System Air"
    )
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

  it("свёрнутый стандарт показывает счётчик позиций (склонение)", async () => {
    renderAt()
    expect(await screen.findByText("1 позиция")).toBeInTheDocument()
  })

  it("пустой вендор: заголовок + «нигде не разрешён», без легенды про зачёркивание", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({ standards: [] })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(screen.getByText("Где разрешён")).toBeInTheDocument()
    expect(await screen.findByText("нигде не разрешён")).toBeInTheDocument()
    expect(screen.queryByText(/зачёркнутый класс/)).not.toBeInTheDocument()
  })

  it("данные без исключённых: легенда без пояснения про зачёркивание", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({
          standards: [
            {
              building_type_id: 1,
              building_type_name: "Жилой дом",
              position_count: 1,
              positions: [
                {
                  position_id: 100,
                  position_name: "Радиаторы отопления",
                  chips: [
                    {
                      segment_id: 11,
                      segment_name: "Делюкс",
                      state: "allowed",
                      release_label: null,
                    },
                  ],
                },
              ],
            },
          ],
        })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(
      await screen.findByText("показано текущее состояние стандартов")
    ).toBeInTheDocument()
    expect(screen.queryByText(/зачёркнутый класс/)).not.toBeInTheDocument()
  })
})

describe("VendorCardScreen — мутации", () => {
  it("клик по тумблеру шлёт PUT /agreement", async () => {
    let putBody: unknown = null
    server.use(
      http.put("/api/vendors/:vendorId/agreement", async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json({ starred: false })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(
      screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })
    )
    await waitFor(() => expect(putBody).toEqual({ active: false }))
  })

  it("добавление alias шлёт POST", async () => {
    let posted: unknown = null
    server.use(
      http.post("/api/vendors/:vendorId/aliases", async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ id: 9, alias: "NewAlias" }, { status: 201 })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByRole("button", { name: "+ вариант" }))
    await userEvent.type(
      screen.getByPlaceholderText("вариант написания"),
      "NewAlias"
    )
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }))
    await waitFor(() => expect(posted).toEqual({ alias: "NewAlias" }))
  })
})
