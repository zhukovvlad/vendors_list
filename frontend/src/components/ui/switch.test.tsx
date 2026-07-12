import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Switch } from "./switch"

describe("Switch", () => {
  it("рендерит роль switch и отражает checked", () => {
    render(<Switch checked disabled aria-label="тест" />)
    expect(screen.getByRole("switch")).toBeChecked()
  })
})
