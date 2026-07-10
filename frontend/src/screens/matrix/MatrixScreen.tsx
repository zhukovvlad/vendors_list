import {
  getCoreRowModel,
  useReactTable,
  flexRender,
} from "@tanstack/react-table"
import { useEffect, useMemo, useState } from "react"

import { matrixRoute } from "@/router"
import { useMatrix, useBuildingTypes, useSegments } from "@/api/queries"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"

import { buildColumnDefs } from "./columns"
import { withSectionHeaders, type MatrixRow } from "./model"

const PAGE_SIZE = 50 // единый источник: limit запроса и шаг пагинатора (не хардкодить дважды)

// Стабильный фолбэк для useReactTable: инлайновый `?? []` создаёт НОВЫЙ массив на
// каждый рендер — нестабильная ссылка data это документированная ловушка
// бесконечного ре-рендера TanStack Table (окно, пока данные не пришли).
const EMPTY_ITEMS: MatrixRow[] = []

export function MatrixScreen() {
  const search = matrixRoute.useSearch()
  const navigate = matrixRoute.useNavigate()

  const buildingTypes = useBuildingTypes()
  const segments = useSegments(search.building_type_id)

  const matrix = useMatrix({
    building_type_id: search.building_type_id ?? 0,
    segment_id: search.segment_id,
    q: search.q || undefined,
    limit: PAGE_SIZE,
    offset: search.offset,
  })

  // Поиск: инпут контролируется ЛОКАЛЬНЫМ состоянием, а не search.q. navigate у
  // TanStack Router асинхронный — если привязать value прямо к search.q, при
  // быстром вводе значение "отскакивает" (search.q не успевает обновиться), и поле
  // подвисает. Локальное состояние обновляется синхронно; в URL пишем с дебаунсом.
  const [qInput, setQInput] = useState(search.q ?? "")

  // Синхронизация из URL (back/forward, внешняя навигация).
  useEffect(() => {
    setQInput(search.q ?? "")
  }, [search.q])

  // Дебаунс: локальный ввод → URL (не на каждый символ). Гвард qInput === search.q
  // не даёт двум эффектам зациклиться.
  useEffect(() => {
    if (qInput === (search.q ?? "")) return
    const t = setTimeout(() => {
      navigate({
        search: (p) => ({ ...p, q: qInput || undefined, offset: 0 }),
      })
    }, 300)
    return () => clearTimeout(t)
  }, [qInput, search.q, navigate])

  const columns = useMemo(
    () => buildColumnDefs(matrix.data?.columns ?? []),
    [matrix.data?.columns]
  )
  const table = useReactTable({
    data: matrix.data?.items ?? EMPTY_ITEMS,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })
  const leafCount = table.getAllLeafColumns().length

  // Пустое состояние: типов объектов нет (свежая БД) — не падаем.
  if (buildingTypes.data && buildingTypes.data.length === 0) {
    return (
      <div className="p-8 text-muted-foreground">
        Типы объектов не заведены.
      </div>
    )
  }

  const displayRows = withSectionHeaders(matrix.data?.items ?? EMPTY_ITEMS)
  // Сопоставление position_id → строка таблицы один раз (иначе .find() на каждую
  // отображаемую строку — O(n²) по строкам страницы).
  const rowByPos = new Map(
    table.getRowModel().rows.map((r) => [r.original.position_id, r])
  )

  return (
    <div className="flex flex-col gap-4 p-6 text-foreground">
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Тип объекта
            <select
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              value={search.building_type_id ?? ""}
              onChange={(e) =>
                navigate({
                  search: (p) => ({
                    ...p,
                    building_type_id: Number(e.target.value),
                    segment_id: undefined,
                    offset: 0,
                  }),
                })
              }
            >
              {buildingTypes.data?.map((bt) => (
                <option key={bt.id} value={bt.id}>
                  {bt.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Класс
            <select
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              value={search.segment_id ?? ""}
              onChange={(e) =>
                navigate({
                  search: (p) => ({
                    ...p,
                    segment_id: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                    offset: 0,
                  }),
                })
              }
            >
              <option value="">Все классы</option>
              {segments.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-muted-foreground">
            Поиск
            <input
              className="rounded-md border border-border bg-background px-2 py-1 text-body text-foreground"
              value={qInput}
              placeholder="позиция / вендор / раздел"
              onChange={(e) => setQInput(e.target.value)}
            />
          </label>
        </CardContent>
      </Card>

      {matrix.isError && (
        <div className="text-destructive">Ошибка загрузки матрицы.</div>
      )}

      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id} colSpan={h.colSpan}>
                  {h.isPlaceholder
                    ? null
                    : flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {displayRows.map((dr) =>
            dr.kind === "section" ? (
              <TableRow key={dr.key} className="bg-muted/40">
                <TableCell
                  colSpan={leafCount}
                  className="text-caption font-medium text-muted-foreground"
                >
                  {dr.categoryPath}
                </TableCell>
              </TableRow>
            ) : (
              <TableRow key={dr.key}>
                {rowByPos
                  .get(dr.row.position_id)
                  ?.getVisibleCells()
                  .map((c) => (
                    <TableCell key={c.id}>
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </TableCell>
                  ))}
              </TableRow>
            )
          )}
        </TableBody>
      </Table>

      <div className="flex items-center gap-3 text-caption text-muted-foreground">
        <span>
          {search.segment_id ? "Позиций в классе" : "Позиций"}:{" "}
          {matrix.data?.total ?? 0}
        </span>
        <Button
          variant="outline"
          disabled={search.offset === 0}
          onClick={() =>
            navigate({
              search: (p) => ({
                ...p,
                offset: Math.max(0, ("offset" in p ? p.offset : 0) - PAGE_SIZE),
              }),
            })
          }
        >
          Назад
        </Button>
        <Button
          variant="outline"
          disabled={
            (matrix.data?.offset ?? 0) + PAGE_SIZE >= (matrix.data?.total ?? 0)
          }
          onClick={() =>
            navigate({
              search: (p) => ({
                ...p,
                offset: ("offset" in p ? p.offset : 0) + PAGE_SIZE,
              }),
            })
          }
        >
          Вперёд
        </Button>
      </div>
    </div>
  )
}
