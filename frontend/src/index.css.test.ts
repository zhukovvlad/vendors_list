import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

const css = readFileSync("src/index.css", "utf-8")

describe("warning status token", () => {
  it("объявлен в светлой теме (:root)", () => {
    expect(css).toMatch(/:root\s*\{[^}]*--warning:\s*#9A6636/s)
  })
  it("объявлен в тёмной теме (.dark)", () => {
    expect(css).toMatch(/\.dark\s*\{[^}]*--warning:\s*#BD9375/s)
  })
  it("замаплен в утилиту через @theme inline", () => {
    expect(css).toMatch(/--color-warning:\s*var\(--warning\)/)
  })
})
