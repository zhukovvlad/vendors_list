import { describe, expect, it } from "vitest"

import type { components } from "@/api/schema"

import { cellFor, withSectionHeaders } from "./model"

type MatrixRow = components["schemas"]["MatrixRow"]

const row = (position_id: number, category_path: string): MatrixRow => ({
  position_id,
  position_name: `p${position_id}`,
  category_path,
  cells: [{ segment_id: 11, vendors: [], spec_text: "Россия", note: null }],
})

describe("withSectionHeaders", () => {
  it("вставляет заголовок на смене category_path", () => {
    const out = withSectionHeaders([row(1, "A"), row(2, "A"), row(3, "B")])
    const kinds = out.map((r) => r.kind)
    expect(kinds).toEqual([
      "section",
      "position",
      "position",
      "section",
      "position",
    ])
  })

  it("печатает заголовок на первой строке страницы, даже если раздел продолжается (дубль на границе — намеренно)", () => {
    // Страница N+1 начинается с продолжения раздела 'A' — заголовок ДОЛЖЕН быть.
    const out = withSectionHeaders([row(4, "A"), row(5, "A")])
    expect(out[0].kind).toBe("section")
    expect(out[0].kind === "section" && out[0].categoryPath).toBe("A")
  })
})

describe("cellFor", () => {
  it("находит ячейку по segment_id, иначе null", () => {
    const r = row(1, "A")
    expect(cellFor(r, 11)?.spec_text).toBe("Россия")
    expect(cellFor(r, 999)).toBeNull()
  })
})
