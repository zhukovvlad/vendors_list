import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { Star, X } from "lucide-react"

import {
  useAddAlias,
  useRemoveAlias,
  useToggleAgreement,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import {
  excludedTooltip,
  hasExcludedChips,
  kindLabel,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)
  const whereAllowed = useVendorWhereAllowed(id)
  const toggleAgreement = useToggleAgreement(id)
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")

  if (isPending)
    return (
      <div className="py-16 text-center text-muted-foreground">Загрузка…</div>
    )
  if (isError || !data)
    return (
      <div className="py-16 text-center text-muted-foreground">
        Вендор не найден
      </div>
    )

  const standards = whereAllowed.data?.standards ?? []

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-h3 font-medium">{data.name}</h1>
          <Badge variant="outline">{kindLabel(data.kind)}</Badge>
          {data.starred && (
            <Badge variant="outline" className="gap-1">
              <Star className="size-3 fill-current" aria-hidden />
              соглашение
            </Badge>
          )}
          <span className="flex-1" />
          <label className="flex items-center gap-2 text-small">
            Соглашение
            <Switch
              checked={data.starred}
              disabled={toggleAgreement.isPending}
              onCheckedChange={(next) => toggleAgreement.mutate(next)}
              aria-label="Соглашение о сотрудничестве"
            />
          </label>
        </div>
        <div className="text-small text-muted-foreground">
          {data.represents ? (
            <>
              представляет:{" "}
              <Link
                to="/vendors/$vendorId"
                params={{ vendorId: String(data.represents.id) }}
                className="underline"
              >
                {data.represents.name}
              </Link>
            </>
          ) : (
            "самостоятельный бренд"
          )}
        </div>
      </header>

      {data.note && (
        <p data-testid="vendor-note" className="text-small">
          {data.note}
        </p>
      )}

      <section className="space-y-2">
        <div className="text-caption text-muted-foreground uppercase">
          Варианты написания
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">—</span>
          )}
          {data.aliases.map((a) => (
            <Badge key={a.id} variant="outline" className="gap-1">
              {a.alias}
              <button
                type="button"
                aria-label={`удалить ${a.alias}`}
                onClick={() => removeAlias.mutate(a.id)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          {aliasOpen ? (
            <span className="flex items-center gap-1">
              <input
                autoFocus
                value={aliasDraft}
                onChange={(e) => setAliasDraft(e.target.value)}
                placeholder="вариант написания"
                className="h-7 rounded-sm border bg-transparent px-2 text-small"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={aliasDraft.trim() === "" || addAlias.isPending}
                onClick={() => {
                  addAlias.mutate(aliasDraft.trim(), {
                    onSuccess: () => {
                      setAliasDraft("")
                      setAliasOpen(false)
                    },
                  })
                }}
              >
                Добавить
              </Button>
            </span>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAliasOpen(true)}
            >
              + вариант
            </Button>
          )}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-caption text-muted-foreground uppercase">
          Бренд и объединение
        </div>
        {data.represented_count > 0 && (
          <div className="text-small text-muted-foreground">
            {data.represented_count} брендов представлены этим
          </div>
        )}
        <Button variant="outline" disabled title="в разработке">
          Объединить
        </Button>
      </section>

      <section className="space-y-2">
        <div className="text-caption text-muted-foreground uppercase">
          Где разрешён
        </div>
        {whereAllowed.isPending ? (
          <div className="text-small text-muted-foreground">Загрузка…</div>
        ) : whereAllowed.isError ? (
          <div className="text-small text-muted-foreground">
            Не удалось загрузить
          </div>
        ) : standards.length === 0 ? (
          <div className="text-small text-muted-foreground">
            {WHERE_ALLOWED_EMPTY}
          </div>
        ) : (
          <>
            <Accordion type="multiple">
              {standards.map((s) => (
                <AccordionItem
                  key={s.building_type_id}
                  value={String(s.building_type_id)}
                >
                  <AccordionTrigger>
                    <span className="flex-1 text-left">
                      {s.building_type_name}
                    </span>
                    <span className="text-small text-muted-foreground">
                      {s.position_count} позиций
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {s.positions.map((p) => (
                      <div key={p.position_id} className="space-y-1.5">
                        <div className="text-small">{p.position_name}</div>
                        <div className="flex flex-wrap gap-1.5">
                          {p.chips.map((c) =>
                            c.state === "allowed" ? (
                              <Badge key={c.segment_id} variant="outline">
                                {c.segment_name}
                              </Badge>
                            ) : (
                              <Badge
                                key={c.segment_id}
                                variant="outline"
                                className="border-dashed text-muted-foreground line-through"
                                title={excludedTooltip(c.release_label)}
                                aria-label={excludedTooltip(c.release_label)}
                              >
                                {c.segment_name}
                              </Badge>
                            )
                          )}
                        </div>
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
            <p className="text-caption text-muted-foreground">
              {whereAllowedLegend(hasExcludedChips(standards))}
            </p>
          </>
        )}
      </section>
    </div>
  )
}
