import { createColumnHelper, type ColumnDef } from "@tanstack/react-table"
import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { components } from "@/api/schema"

import { cellFor, type MatrixCell, type MatrixRow } from "./model"

type MatrixColumnGroup = components["schemas"]["MatrixColumnGroup"]

export function renderCell(cell: MatrixCell | null) {
  if (!cell) return <span className="text-muted-foreground/60">—</span>
  if (cell.vendors.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {cell.vendors.map((v) => (
          <Link
            key={v.vendor_id}
            to="/vendors/$vendorId"
            params={{ vendorId: String(v.vendor_id) }}
            className="rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span
              title={v.note ?? undefined}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-caption whitespace-nowrap transition-colors",
                v.starred
                  ? "border-chart-2/40 bg-chart-2/10 text-foreground hover:border-chart-2/60"
                  : "border-border-strong bg-card text-foreground hover:bg-accent"
              )}
            >
              {v.starred && (
                <Star
                  className="size-3 fill-current text-chart-2"
                  aria-label="действующее соглашение"
                />
              )}
              {v.name}
              {v.ujin_integration && (
                <span className="ml-0.5 border-l border-border-strong pl-1 text-[10px] tracking-wide text-muted-foreground">
                  Ujin
                </span>
              )}
            </span>
          </Link>
        ))}
      </div>
    )
  }
  if (cell.spec_text)
    return <Badge variant="requirement">{cell.spec_text}</Badge>
  return <span className="text-muted-foreground/60">—</span>
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
