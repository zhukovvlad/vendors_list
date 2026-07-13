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

import { ThemeProvider } from "@/components/theme-provider"
import { routeTree } from "@/router"
import { server } from "@/test/msw/server"
import { vendorFixture, whereAllowedFixture } from "@/test/msw/handlers"

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
  return qc
}

async function enterEditMode() {
  await userEvent.click(screen.getByRole("button", { name: "Редактировать" }))
}

describe("VendorCardScreen — режим правки", () => {
  it("view по умолчанию: ноль affordance", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(
      screen.getByRole("button", { name: "Редактировать" })
    ).toBeInTheDocument()
    // тумблер соглашения выключен/недоступен
    expect(
      screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })
    ).toBeDisabled()
    // нет инлайн-кнопок правки, нет «×» на алиасах, нет «+ вариант»
    expect(
      screen.queryByRole("button", { name: "Редактировать имя" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /удалить/ })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "вариант" })
    ).not.toBeInTheDocument()
  })

  it("вход в edit: появляются affordance и баннер", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    expect(screen.getByRole("button", { name: "Готово" })).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Редактировать имя" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("switch", { name: "Соглашение о сотрудничестве" })
    ).not.toBeDisabled()
    // дефолтная фикстура уже содержит легенду про «войдут в следующий релиз»
    // (excluded-чип «Бизнес»), поэтому проверяем баннер по уникальной фразе
    expect(screen.getByText(/применяются\s+немедленно/)).toBeInTheDocument()
  })

  it("вход в edit: все стандарты раскрыты", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    // дефолтная фикстура: 1 стандарт «Жилой дом» → раскрыт (виден чип)
    expect(await screen.findByText("Делюкс")).toBeInTheDocument()
  })

  it("вход в edit ДО загрузки where-allowed: секции раскрываются после прихода данных", async () => {
    // Вендор (шапка+кнопка) грузится сразу, where-allowed держим «в пути»
    // (никогда не отвечающий хендлер) → вход в edit при standards=[]. Затем
    // имитируем приход дерева через кэш и ждём авто-раскрытия секций.
    server.use(
      http.get(
        "/api/vendors/:vendorId/where-allowed",
        () => new Promise<never>(() => {}) // никогда не резолвится
      )
    )
    const qc = renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode() // стандарты ещё не пришли
    // дерево приходит уже в edit-режиме
    qc.setQueryData(["vendor-where-allowed", 5], whereAllowedFixture)
    // секция раскрыта: контент смонтирован (чип виден)
    expect(await screen.findByText("Делюкс")).toBeInTheDocument()
  })
})

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
    await enterEditMode()
    expect(
      screen.getByRole("button", { name: "Редактировать примечание" })
    ).toHaveTextContent("+ примечание")
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

  it("показывает аватар-инициал и пустое состояние алиасов", async () => {
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, aliases: [] })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(screen.getByText("S")).toBeInTheDocument() // инициал аватара
    expect(screen.getByText("вариантов пока нет")).toBeInTheDocument()
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
      "Был в релизе «ред. 25.03.2026», исключён — войдёт в следующий релиз"
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
      await screen.findByText(/исключения войдут в следующий релиз/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/зачёркнутый класс/)).not.toBeInTheDocument()
  })

  it("показывает сводку «N стандартов · M позиций»", async () => {
    renderAt()
    expect(
      await screen.findByText("1 стандарт · 1 позиция")
    ).toBeInTheDocument()
  })

  it("полное покрытие без excluded → чип «все классы» вместо перечня", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({
          standards: [
            {
              building_type_id: 1,
              building_type_name: "Жилой дом",
              position_count: 1,
              segment_count: 2,
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
                    {
                      segment_id: 12,
                      segment_name: "Эконом",
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
    const trigger = screen.getByRole("button", { name: /Жилой дом/ })
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute("data-state", "open")
    expect(await screen.findByText("все классы")).toBeInTheDocument()
    expect(screen.queryByText("Делюкс")).not.toBeInTheDocument()
  })

  it("стандарт, где все позиции покрыты → сводка «· все классы» в заголовке", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({
          standards: [
            {
              building_type_id: 1,
              building_type_name: "Жилой дом",
              position_count: 1,
              segment_count: 1,
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
      await screen.findByText(/1 позиция · все классы/)
    ).toBeInTheDocument()
  })

  it("легенда без рамки: при excluded — образец-чип и пояснение", async () => {
    renderAt() // дефолтная фикстура содержит excluded «Бизнес»
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    expect(
      await screen.findByText(/исключён, войдёт в следующий релиз/)
    ).toBeInTheDocument()
  })

  it("уточнение позиции в скобках приглушено (split)", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({
          standards: [
            {
              building_type_id: 1,
              building_type_name: "Жилой дом",
              position_count: 1,
              segment_count: 2,
              positions: [
                {
                  position_id: 100,
                  position_name: "Насосы (EC двигатель)",
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
    await userEvent.click(screen.getByRole("button", { name: /Жилой дом/ }))
    expect(await screen.findByText("(EC двигатель)")).toBeInTheDocument()
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
    await enterEditMode()
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
    await enterEditMode()
    await userEvent.click(screen.getByRole("button", { name: "вариант" }))
    await userEvent.type(
      screen.getByPlaceholderText("вариант написания"),
      "NewAlias"
    )
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }))
    await waitFor(() => expect(posted).toEqual({ alias: "NewAlias" }))
  })
})

describe("VendorCardScreen — инлайн-правка шапки", () => {
  it("клик по имени → инпут в h1; Enter шлёт PATCH {name}", async () => {
    let patched: unknown = null
    server.use(
      http.patch("/api/vendors/:vendorId", async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...vendorFixture, name: "System Air 2" })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать имя" })
    )
    const input = screen.getByRole("textbox", { name: "Редактировать имя" })
    await userEvent.clear(input)
    await userEvent.type(input, "System Air 2{Enter}")
    await waitFor(() => expect(patched).toEqual({ name: "System Air 2" }))
    // инпут имени живёт внутри h1 (пр.4)
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument()
  })

  it("409 на имени → инлайн-ошибка, остаёмся в правке", async () => {
    server.use(
      http.patch("/api/vendors/:vendorId", () =>
        HttpResponse.json({ detail: "Имя уже занято" }, { status: 409 })
      )
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать имя" })
    )
    const input = screen.getByRole("textbox", { name: "Редактировать имя" })
    await userEvent.clear(input)
    await userEvent.type(input, "Занятое{Enter}")
    expect(await screen.findByRole("alert")).toHaveTextContent("Имя уже занято")
    expect(
      screen.getByRole("textbox", { name: "Редактировать имя" })
    ).toBeInTheDocument()
  })

  it("правка примечания шлёт PATCH {note}", async () => {
    let patched: unknown = null
    server.use(
      http.patch("/api/vendors/:vendorId", async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...vendorFixture, note: "заметка" })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать примечание" })
    )
    await userEvent.type(
      screen.getByRole("textbox", { name: "Редактировать примечание" }),
      "заметка"
    )
    await userEvent.tab() // blur сохраняет
    await waitFor(() => expect(patched).toEqual({ note: "заметка" }))
  })

  it('очистка примечания шлёт PATCH {note: ""}', async () => {
    let patched: unknown = null
    server.use(
      http.get("/api/vendors/:vendorId", () =>
        HttpResponse.json({ ...vendorFixture, note: "старая заметка" })
      ),
      http.patch("/api/vendors/:vendorId", async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...vendorFixture, note: null })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать примечание" })
    )
    const box = screen.getByRole("textbox", {
      name: "Редактировать примечание",
    })
    await userEvent.clear(box)
    await userEvent.tab() // blur сохраняет (multiline)
    await waitFor(() => expect(patched).toEqual({ note: "" }))
  })
})

describe("VendorCardScreen — операции разрешений", () => {
  /** Перехватывает тело POST /listings/exclude; по умолчанию отвечает успехом. */
  function stubExclude(errorStatus?: number) {
    const captured: { body: unknown } = { body: null }
    server.use(
      http.post(
        "/api/vendors/:vendorId/listings/exclude",
        async ({ request }) => {
          captured.body = await request.json()
          if (errorStatus !== undefined) {
            // JSON-тело обязательно: без него openapi-fetch не заполнит `error`,
            // и мутация ошибочно считается успешной.
            return HttpResponse.json(
              { detail: "конфликт" },
              { status: errorStatus }
            )
          }
          return HttpResponse.json({
            excluded_positions: 1,
            excluded_classes: 2,
          })
        }
      )
    )
    return captured
  }

  it("класс «×» → мгновенная мутация scope=class без диалога", async () => {
    const captured = stubExclude()
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: /исключить класс Делюкс/ })
    )
    await waitFor(() =>
      expect(captured.body).toMatchObject({
        scope: "class",
        position_id: 100,
        segment_id: 11,
      })
    )
    // точечное исключение — без диалога подтверждения
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("«⊖» позиции → подтверждение → мутация scope=position, диалог закрывается", async () => {
    const captured = stubExclude()
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: /исключить из позиции/ })
    )
    expect(await screen.findByText(/Будет исключён из/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Исключить" }))
    await waitFor(() =>
      expect(captured.body).toMatchObject({
        scope: "position",
        position_id: 100,
        building_type_id: 1,
      })
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })

  it("kebab стандарта → подтверждение → мутация scope=standard, диалог закрывается", async () => {
    const captured = stubExclude()
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: /действия стандарта/ })
    )
    await userEvent.click(await screen.findByText("Исключить из стандарта"))
    expect(await screen.findByText(/Будет исключён из/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Исключить" }))
    await waitFor(() =>
      expect(captured.body).toMatchObject({
        scope: "standard",
        building_type_id: 1,
      })
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })

  it("отказ мутации исключения → диалог остаётся открытым", async () => {
    const captured = stubExclude(409)
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(
      screen.getByRole("button", { name: /исключить из позиции/ })
    )
    await screen.findByText(/Будет исключён из/)
    await userEvent.click(screen.getByRole("button", { name: "Исключить" }))
    // запрос ушёл и провалился (409) — но диалог НЕ закрывается: пользователь
    // видит контекст и может повторить (закрытие только на успехе).
    await waitFor(() => expect(captured.body).not.toBeNull())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})

describe("VendorCardScreen — + стандарт", () => {
  it("открывает диалог; присутствующий стандарт приглушён", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    await userEvent.click(screen.getByRole("button", { name: "+ стандарт" }))
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    // «Жилой дом» присутствует (id=1 в where-allowed) → помечен «уже присутствует»
    expect(await screen.findByText(/уже присутствует/)).toBeInTheDocument()
  })

  /** Проводит диалог через все 3 шага: стандарт (ещё не присутствующий id=2) →
   * позиция → класс. Оставляет клик по «Добавить» вызывающему тесту, чтобы тот
   * мог выбрать между success- и error-обработчиком POST. */
  async function fillAddStandardSteps() {
    await enterEditMode()
    await userEvent.click(screen.getByRole("button", { name: "+ стандарт" }))
    const dialog = await screen.findByRole("dialog")
    await userEvent.click(
      within(dialog).getByRole("radio", { name: /Офисные здания/ })
    )
    await userEvent.click(
      await within(dialog).findByText("Радиаторы отопления")
    )
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: "Бизнес" })
    )
    return dialog
  }

  it("сабмит: POST уходит с ожидаемым телом, диалог закрывается", async () => {
    let posted: unknown = null
    server.use(
      http.post("/api/vendors/:vendorId/listings", async ({ request }) => {
        posted = await request.json()
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    const dialog = await fillAddStandardSteps()
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Добавить" })
    )
    await waitFor(() =>
      expect(posted).toEqual({ position_id: 100, segment_ids: [11] })
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })

  it("409 на добавлении → диалог остаётся открытым (не глотает отказ)", async () => {
    let handled = false
    server.use(
      http.post("/api/vendors/:vendorId/listings", () => {
        handled = true
        return HttpResponse.json({ detail: "конфликт" }, { status: 409 })
      })
    )
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    const dialog = await fillAddStandardSteps()
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Добавить" })
    )
    // мутация отработала (отказ), но диалог остаётся смонтированным и открытым
    await waitFor(() => expect(handled).toBe(true))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})

describe("VendorCardScreen — клиппинг edit + полоса + типографика v4", () => {
  it("edit-режим: контент секции без overflow-hidden и анимации (не клиппится)", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    // в edit секции раскрыты принудительно → контент смонтирован
    const contents = document.querySelectorAll(
      '[data-slot="accordion-content"]'
    )
    expect(contents.length).toBeGreaterThan(0)
    contents.forEach((el) => {
      expect(el.className).not.toContain("overflow-hidden")
      expect(el.className).not.toContain("animate-accordion")
    })
  })

  it("view-режим: раскрытая секция сохраняет overflow-hidden + анимацию", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByRole("button", { name: /Жилой дом/ }))
    await screen.findByText("Делюкс") // дождаться монтирования контента
    const content = document.querySelector('[data-slot="accordion-content"]')
    expect(content).not.toBeNull()
    expect(content!.className).toContain("overflow-hidden")
    expect(content!.className).toContain("animate-accordion")
  })

  it("edit-режим: «+ стандарт» отрендерен выше легенды", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await enterEditMode()
    const plus = screen.getByRole("button", { name: "+ стандарт" })
    const legend = screen.getByText(/исключён, войдёт в следующий релиз/)
    // +стандарт предшествует легенде в порядке документа
    expect(
      plus.compareDocumentPosition(legend) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it("edit-режим: полоса стандарта без счётчика позиций", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    // view: счётчик в полосе присутствует
    expect(
      screen.getByRole("button", { name: /^Жилой дом/ })
    ).toHaveTextContent(/позици/i)
    await enterEditMode()
    // edit: полоса чистая (имя-триггер без счётчика; `^` отсекает кебаб)
    expect(
      screen.getByRole("button", { name: /^Жилой дом/ })
    ).not.toHaveTextContent(/позици/i)
  })

  it("edit-режим: сводка «все классы» не рендерится в полосе", async () => {
    server.use(
      http.get("/api/vendors/:vendorId/where-allowed", () =>
        HttpResponse.json({
          standards: [
            {
              building_type_id: 1,
              building_type_name: "Жилой дом",
              position_count: 1,
              segment_count: 1,
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
    // view: сводка «все классы» в полосе видна
    expect(
      await screen.findByText(/1 позиция · все классы/)
    ).toBeInTheDocument()
    await enterEditMode()
    expect(
      screen.getByRole("button", { name: /^Жилой дом/ })
    ).not.toHaveTextContent(/все классы/i)
  })

  it("v4: полоса — caption/uppercase; имя позиции — 15px; размеры разные", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByRole("button", { name: /Жилой дом/ }))
    const stripName = screen.getByText("Жилой дом")
    const posName = await screen.findByText("Радиаторы отопления")
    expect(stripName.className).toContain("uppercase")
    expect(stripName.className).toContain("text-caption")
    expect(posName.className).toContain("text-[15px]")
    // разные размерные классы (не оба 14px text-small, как в v3)
    expect(stripName.className).not.toContain("text-[15px]")
    expect(posName.className).not.toContain("text-caption")
  })

  it("v4: имя стандарта приглушено даже в раскрытом виде (не text-foreground)", async () => {
    renderAt()
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByRole("button", { name: /^Жилой дом/ }))
    const stripName = screen.getByText("Жилой дом")
    // полоса — «группировка, не контент»: тон muted в обоих состояниях,
    // открытый лишь чуть светлее. Ярким foreground в open быть не должна.
    expect(stripName.className).toContain("text-muted-foreground")
    expect(stripName.className).not.toContain("text-foreground")
  })

  it("v4: чипы классов приглушены (не яркий text-foreground имени позиции)", async () => {
    renderAt() // дефолтная фикстура: allowed-чип «Делюкс»
    await screen.findByRole("heading", { level: 1, name: /System Air/ })
    await userEvent.click(screen.getByRole("button", { name: /^Жилой дом/ }))
    const chip = await screen.findByText("Делюкс")
    expect(chip.className).toContain("text-muted-foreground")
    expect(chip.className).not.toContain("text-[15px]")
  })
})
