import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { InlineEditText } from "./InlineEditText"

describe("InlineEditText", () => {
  it("клик по дисплею открывает инпут со значением", async () => {
    render(<InlineEditText value="Имя" onSubmit={vi.fn()} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    expect(screen.getByRole("textbox")).toHaveValue("Имя")
  })

  it("Enter сохраняет новое значение", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <InlineEditText value="Старое" onSubmit={onSubmit} ariaLabel="Имя" />
    )
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.type(screen.getByRole("textbox"), "Новое{Enter}")
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith("Новое")
  })

  it("Esc отменяет, onSubmit не зовётся, возврат к дисплею", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.type(screen.getByRole("textbox"), "xxx")
    await userEvent.keyboard("{Escape}")
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Имя" })).toBeInTheDocument()
  })

  it("no-op: значение не изменилось → onSubmit не зовётся", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("single + пусто → отмена (имя обязательно)", async () => {
    const onSubmit = vi.fn()
    render(<InlineEditText value="Имя" onSubmit={onSubmit} ariaLabel="Имя" />)
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("reject onSubmit → остаёмся в правке, error виден", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("409"))
    const { rerender } = render(
      <InlineEditText
        value="Имя"
        onSubmit={onSubmit}
        ariaLabel="Имя"
        error={null}
      />
    )
    await userEvent.click(screen.getByRole("button", { name: "Имя" }))
    await userEvent.clear(screen.getByRole("textbox"))
    await userEvent.type(screen.getByRole("textbox"), "Занято{Enter}")
    rerender(
      <InlineEditText
        value="Имя"
        onSubmit={onSubmit}
        ariaLabel="Имя"
        error="Имя уже занято"
      />
    )
    expect(screen.getByRole("textbox")).toBeInTheDocument() // не вышли из правки
    expect(screen.getByRole("alert")).toHaveTextContent("Имя уже занято")
  })

  it("multiline: Enter не сохраняет, blur сохраняет", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <InlineEditText
        value=""
        onSubmit={onSubmit}
        ariaLabel="Примечание"
        multiline
        placeholder="+ примечание"
      />
    )
    await userEvent.click(screen.getByRole("button", { name: "Примечание" }))
    await userEvent.type(screen.getByRole("textbox"), "строка{Enter}ещё")
    expect(onSubmit).not.toHaveBeenCalled() // Enter — перенос строки
    await userEvent.tab() // blur
    expect(onSubmit).toHaveBeenCalledOnce()
  })
})
