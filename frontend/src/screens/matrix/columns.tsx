import { createColumnHelper, type ColumnDef } from "@tanstack/react-table"
import { Star } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { components } from "@/api/schema"

import { cellFor, type MatrixCell, type MatrixRow } from "./model"

type MatrixColumnGroup = components["schemas"]["MatrixColumnGroup"]

export function renderCell(cell: MatrixCell | null) {
  if (!cell) return <span className="text-muted-foreground">—</span>
  if (cell.vendors.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {cell.vendors.map((v) => (
          <Badge
            key={v.vendor_id}
            variant="outline"
            title={v.note ?? undefined}
          >
            {v.starred && (
              <Star
                className="size-3 fill-current"
                aria-label="действующее соглашение"
              />
            )}
            {v.name}
            {v.ujin_integration && (
              <span className="text-caption text-muted-foreground">Ujin</span>
            )}
          </Badge>
        ))}
      </div>
    )
  }
  if (cell.spec_text)
    return <Badge variant="requirement">{cell.spec_text}</Badge>
  return <span className="text-muted-foreground">—</span>
}

const ch = createColumnHelper<MatrixRow>()

export function buildColumnDefs(
  columns: MatrixColumnGroup[]
): ColumnDef<MatrixRow, unknown>[] {
  const positionCol = ch.display({
    id: "position",
    header: "Позиция",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.position_name}</span>
    ),
  }) as ColumnDef<MatrixRow, unknown>

  const segCols = columns.flatMap((grp) => {
    const leaves = grp.segments.map(
      (s) =>
        ch.display({
          id: String(s.id),
          header: s.name,
          cell: ({ row }) => renderCell(cellFor(row.original, s.id)),
        }) as ColumnDef<MatrixRow, unknown>
    )
    if (!grp.group) return leaves
    return [
      ch.group({
        id: `g${grp.group.id}`,
        header: grp.group.name,
        columns: leaves,
      }) as ColumnDef<MatrixRow, unknown>,
    ]
  })

  return [positionCol, ...segCols]
}
