import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

// Переиспользуем БОЕВОЕ дерево маршрутов — те же route-инстансы, что импортирует
// экран, поэтому строгие matrixRoute.useSearch()/useNavigate() резолвятся в тесте.
import { routeTree } from "@/router"
import { server } from "@/test/msw/server"

function makeRouter(initial = "/?building_type_id=1") {
  return createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
}

function renderWith(router: ReturnType<typeof makeRouter>) {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe("MatrixScreen", () => {
  it("рисует групповые шапки, вендора со звездой, требование и заголовок раздела", async () => {
    renderWith(makeRouter())
    expect(await screen.findByText("Насосы")).toBeInTheDocument()
    expect(screen.getByText("Grundfos")).toBeInTheDocument()
    expect(screen.getByLabelText("действующее соглашение")).toBeInTheDocument()
    expect(screen.getByText("Россия")).toBeInTheDocument()
    expect(screen.getByText("Оборудование / ОВиК")).toBeInTheDocument() // заголовок раздела
    // "Бизнес"/"Эконом" встречаются и в шапках колонок таблицы, и в опциях фильтра
    // "Класс" (те же имена классов из useSegments) — скоупим на таблицу, чтобы
    // getByText не упал на неоднозначности между двумя одинаковыми текстами.
    const table = screen.getByRole("table")
    expect(within(table).getByText("Бизнес")).toBeInTheDocument() // шапки классов
    expect(within(table).getByText("Эконом")).toBeInTheDocument()
  })

  it("серверная пагинация: клик «Вперёд» увеличивает offset в URL на PAGE_SIZE", async () => {
    server.use(
      http.get("/api/listings/matrix", () =>
        HttpResponse.json({
          columns: [
            {
              group: null,
              segments: [{ id: 11, name: "Бизнес", sort_order: 4 }],
            },
          ],
          items: [
            {
              position_id: 100,
              position_name: "Насосы",
              category_path: "Оборудование / ОВиК",
              cells: [
                {
                  segment_id: 11,
                  vendors: [],
                  spec_text: "Россия",
                  note: null,
                },
              ],
            },
          ],
          total: 120, // > PAGE_SIZE ⇒ «Вперёд» активна
          limit: 50,
          offset: 0,
        })
      )
    )
    const router = makeRouter()
    renderWith(router)
    await screen.findByText("Насосы")
    await userEvent.click(screen.getByRole("button", { name: "Вперёд" }))
    await waitFor(() =>
      expect(router.state.location.search).toMatchObject({ offset: 50 })
    )
  })
})
