// @vitest-environment node
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const css = readFileSync(
  fileURLToPath(new URL("./index.css", import.meta.url)),
  "utf-8"
)

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
