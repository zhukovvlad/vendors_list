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
})
