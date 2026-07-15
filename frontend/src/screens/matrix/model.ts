import type { RowData } from "@tanstack/react-table"

import type { components } from "@/api/schema"

export type MatrixRow = components["schemas"]["MatrixRow"]
export type MatrixCell = components["schemas"]["MatrixCell"]

export type DisplayRow =
  | { kind: "section"; categoryPath: string; key: string }
  | { kind: "position"; row: MatrixRow; key: string }

/**
 * Разворачивает страницу позиций в строки отображения, вставляя строку-заголовок
 * раздела на смене category_path. prev сбрасывается на каждый вызов (на страницу),
 * поэтому раздел, продолжающийся с прошлой страницы, печатает заголовок на первой
 * строке новой — это намеренно (контекст на новой странице), НЕ баг.
 */
export function withSectionHeaders(items: MatrixRow[]): DisplayRow[] {
  const out: DisplayRow[] = []
  let prev: string | null = null
  for (const row of items) {
    if (row.category_path !== prev) {
      out.push({
        kind: "section",
        categoryPath: row.category_path,
        key: `sec:${row.category_path}`,
      })
      prev = row.category_path
    }
    out.push({ kind: "position", row, key: `pos:${row.position_id}` })
  }
  return out
}

export function cellFor(row: MatrixRow, segmentId: number): MatrixCell | null {
  return row.cells.find((c) => c.segment_id === segmentId) ?? null
}

// Разрешаем per-column CSS-классы через meta (sticky-колонка, разделители групп).
// TanStack не типизирует meta по умолчанию — расширяем интерфейс.
declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    className?: string
    headerClassName?: string
  }
}
