import { ChevronRight, LockOpen, Users, ArrowsUpFromLine } from "lucide-react"

import { useDashboard } from "@/api/queries"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

import { formatRelative, hasAttention } from "./model"

function Metric({
  label,
  value,
  children,
}: {
  label: string
  value: number
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-caption text-muted-foreground uppercase">
          {label}
        </div>
        <div className="mt-1 text-h3 font-medium">{value}</div>
        <div className="mt-2 text-small text-muted-foreground">{children}</div>
      </CardContent>
    </Card>
  )
}

export function DashboardScreen() {
  const now = new Date()
  const { data, isLoading, isError } = useDashboard()

  if (isError) {
    return <div className="p-6 text-destructive">Ошибка загрузки обзора.</div>
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-3 p-6">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <CardContent className="pt-4">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-2 h-7 w-16" />
                <Skeleton className="mt-3 h-3 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  const { summary, drafts } = data
  const staleDrafts = drafts.filter((d) => d.is_stale)
  const attention = hasAttention(data)

  return (
    <div className="flex flex-col gap-3 p-6 text-foreground">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h3 font-medium">Обзор</h1>
          <div className="text-small text-muted-foreground">
            Ведение вендор-листов
          </div>
        </div>
        {/* Действие отложено: цель (создание стандарта) — будущий срез. */}
        <Button disabled title="Скоро">
          Новый стандарт
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Позиции" value={summary.positions_active}>
          в действующих релизах
        </Metric>
        <Metric
          label="Издания"
          value={summary.releases_published + summary.drafts_open}
        >
          {summary.releases_published} релизов · {summary.drafts_open} черновика
        </Metric>
        <Metric label="Вендоры" value={summary.vendors_total}>
          <span className="flex items-center gap-1">
            <Users className="size-3" /> {summary.vendors_with_agreement} с
            соглашением
          </span>
        </Metric>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardContent className="pt-4">
            <div className="mb-1 text-caption text-muted-foreground uppercase">
              Черновики в работе
            </div>
            {drafts.length === 0 ? (
              <div className="py-4 text-small text-muted-foreground">
                Открытых черновиков нет.
              </div>
            ) : (
              drafts.map((d) => (
                <div
                  key={d.release_id}
                  className="flex items-center gap-3 border-t border-border py-3"
                >
                  <LockOpen className="size-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-small">
                      {d.building_type_name} · {d.label}
                    </div>
                    <div className="text-caption text-muted-foreground">
                      изменён {formatRelative(d.last_touched_at, now)}
                      {d.last_touched_by ? ` · ${d.last_touched_by}` : ""}
                    </div>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="mb-1 text-caption text-muted-foreground uppercase">
              Требует внимания
            </div>
            {!attention ? (
              <div className="py-4 text-small text-muted-foreground">
                Всё чисто.
              </div>
            ) : (
              <>
                {summary.merge_candidate_pairs != null &&
                  summary.merge_candidate_pairs > 0 && (
                    <div className="flex items-center gap-3 border-t border-border py-3">
                      <ArrowsUpFromLine className="size-4 shrink-0 text-primary" />
                      <div className="min-w-0 flex-1 text-small">
                        {summary.merge_candidate_pairs} пар вендоров похожи
                        <div className="text-caption text-muted-foreground">
                          возможные дубли
                        </div>
                      </div>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </div>
                  )}
                {staleDrafts.map((d) => (
                  <div
                    key={d.release_id}
                    className="flex items-center gap-3 border-t border-border py-3"
                  >
                    <LockOpen className="size-4 shrink-0 text-warning" />
                    <div className="min-w-0 flex-1 text-small">
                      {d.building_type_name} · {d.label} залежался
                      <div className="text-caption text-muted-foreground">
                        черновик не менялся давно
                      </div>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
