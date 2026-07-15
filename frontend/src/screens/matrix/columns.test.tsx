import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { renderCell } from "./columns"
import type { MatrixCell } from "./model"

const cell = (over: Partial<MatrixCell>): MatrixCell => ({
  segment_id: 11,
  vendors: [],
  spec_text: null,
  note: null,
  ...over,
})

describe("renderCell", () => {
  it("пустая ячейка → тире", () => {
    render(<>{renderCell(null)}</>)
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("требование → текст spec_text", () => {
    render(<>{renderCell(cell({ spec_text: "Россия" }))}</>)
    expect(screen.getByText("Россия")).toBeInTheDocument()
  })
})
