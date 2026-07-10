import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./table"

describe("Table", () => {
  it("рендерит семантическую таблицу с ячейками", () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Позиция</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Насосы</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )
    expect(
      screen.getByRole("columnheader", { name: "Позиция" })
    ).toBeInTheDocument()
    expect(screen.getByRole("cell", { name: "Насосы" })).toBeInTheDocument()
  })
})
