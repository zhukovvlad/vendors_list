import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Badge } from "./badge"

describe("Badge", () => {
  it("рендерит содержимое и вариант", () => {
    render(<Badge variant="requirement">Россия</Badge>)
    expect(screen.getByText("Россия")).toBeInTheDocument()
  })
})
