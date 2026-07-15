import { createColumnHelper, type ColumnDef } from "@tanstack/react-table"
import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { splitQualifier } from "@/lib/qualifier"
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
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-caption leading-none tracking-normal whitespace-nowrap transition-colors",
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
    return (
      <Badge
        variant="requirement"
        className="max-w-[180px] font-normal tracking-normal whitespace-normal"
      >
        {cell.spec_text}
      </Badge>
    )
  return <span className="text-muted-foreground/60">—</span>
}

const ch = createColumnHelper<MatrixRow>()

export function buildColumnDefs(
  columns: MatrixColumnGroup[]
): ColumnDef<MatrixRow, unknown>[] {
  const positionCol = ch.display({
    id: "position",
    header: "Позиция",
    cell: ({ row }) => {
      const { head, qualifier } = splitQualifier(row.original.position_name)
      return (
        <span className="leading-tight font-medium">
          {head}
          {qualifier && (
            <span className="block text-caption font-normal tracking-normal text-muted-foreground">
              {qualifier}
            </span>
          )}
        </span>
      )
    },
    meta: {
      // group-hover: подсветка липкой ячейки вместе со строкой (её opaque bg-card
      // маскирует hover:bg-muted/50 строки — нужен собственный group-hover).
      className:
        "sticky left-0 z-[2] min-w-[190px] bg-card border-r border-border group-hover:bg-muted/50",
      headerClassName: "sticky left-0 z-[4] bg-muted border-r border-border",
    },
  }) as ColumnDef<MatrixRow, unknown>

  const segCols = columns.flatMap((grp, gi) => {
    // Левый разделитель — МЕЖДУ группами; у первой группы не рисуем, иначе двойная
    // линия вплотную к border-r липкой «Позиции».
    const border = gi > 0 ? "border-l border-border" : undefined
    const leaves = grp.segments.map(
      (s, idx) =>
        ch.display({
          id: String(s.id),
          header: s.name,
          cell: ({ row }) => renderCell(cellFor(row.original, s.id)),
          meta:
            idx === 0 && border
              ? { className: border, headerClassName: border }
              : undefined,
        }) as ColumnDef<MatrixRow, unknown>
    )
    if (!grp.group) return leaves
    return [
      ch.group({
        id: `g${grp.group.id}`,
        header: grp.group.name,
        columns: leaves,
        meta: { headerClassName: cn(border, "text-center") },
      }) as ColumnDef<MatrixRow, unknown>,
    ]
  })

  return [positionCol, ...segCols]
}
