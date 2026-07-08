import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Button } from "@/components/ui/button"

describe("Button", () => {
  it("рендерит текст и слот-атрибут", () => {
    render(<Button>Сохранить</Button>)
    const btn = screen.getByRole("button", { name: "Сохранить" })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute("data-slot", "button")
  })

  it("контролы: радиус md и вес normal (DS)", () => {
    render(<Button>Ок</Button>)
    const btn = screen.getByRole("button", { name: "Ок" })
    expect(btn.className).toContain("rounded-md")
    expect(btn.className).toContain("font-normal")
  })

  it("subtle-вариант: фиолетовая подложка через --accent-subtle", () => {
    render(<Button variant="subtle">Тон</Button>)
    const btn = screen.getByRole("button", { name: "Тон" })
    expect(btn).toHaveAttribute("data-variant", "subtle")
    expect(btn.className).toContain("var(--accent-subtle)")
  })

  it("destructive-вариант: сплошная заливка danger", () => {
    render(<Button variant="destructive">Удалить</Button>)
    const btn = screen.getByRole("button", { name: "Удалить" })
    expect(btn.className).toContain("var(--destructive-solid)")
  })
})
