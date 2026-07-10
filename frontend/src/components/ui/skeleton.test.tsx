import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Skeleton } from "./skeleton"

describe("Skeleton", () => {
  it("рендерит плейсхолдер с анимацией и токен-фоном (не сырой примитив)", () => {
    const { container } = render(<Skeleton className="h-4 w-10" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain("animate-pulse")
    expect(el.className).toContain("bg-accent")
    expect(el.className).toContain("h-4")
  })
})
