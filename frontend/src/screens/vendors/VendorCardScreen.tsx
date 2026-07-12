import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { Accordion as AccordionPrimitive } from "radix-ui"
import { Award, ChevronRight, Merge, Plus, Star, X } from "lucide-react"

import {
  useAddAlias,
  useRemoveAlias,
  useToggleAgreement,
  useUpdateVendorHeader,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import {
  avatarInitial,
  excludedTooltip,
  hasExcludedChips,
  isAllClasses,
  kindLabel,
  pluralPositions,
  pluralStandards,
  pluralVendors,
  standardAllClasses,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"
import { InlineEditText } from "./InlineEditText"

const CARD = "rounded-xl border border-border bg-card"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)
  const whereAllowed = useVendorWhereAllowed(id)
  const toggleAgreement = useToggleAgreement(id)
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const updateHeader = useUpdateVendorHeader(id)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")
  const [nameError, setNameError] = useState<string | null>(null)

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
  const positionTotal = standards.reduce((a, s) => a + s.position_count, 0)

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-3 py-6">
      {/* Шапка */}
      <section className={`${CARD} px-5 py-[18px]`}>
        <div className="flex items-center gap-3.5">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-border bg-accent text-h3 font-medium text-primary">
            {avatarInitial(data.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="min-w-0 text-h3 font-medium tracking-tight">
                <InlineEditText
                  value={data.name}
                  ariaLabel="Редактировать имя"
                  onEditStart={() => setNameError(null)}
                  error={nameError}
                  displayClassName="max-w-full truncate text-left hover:opacity-80"
                  inputClassName="w-full rounded-md border border-border bg-transparent px-1 text-h3 font-medium outline-none focus-visible:border-ring"
                  onSubmit={async (next) => {
                    setNameError(null)
                    try {
                      await updateHeader.mutateAsync({ name: next })
                    } catch (e) {
                      // Единственный ожидаемый отказ правки имени — 409 (занято);
                      // прочее маловероятно, сообщение по сути не вводит в заблуждение.
                      setNameError("Имя уже занято")
                      throw e
                    }
                  }}
                />
              </h1>
              <Badge variant="outline" className="rounded-full">
                {kindLabel(data.kind)}
              </Badge>
              {data.starred && (
                <Badge variant="outline" className="gap-1 rounded-full">
                  <Star className="size-3 fill-current" aria-hidden />
                  соглашение
                </Badge>
              )}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-small text-muted-foreground">
              <Award className="size-3.5 shrink-0" aria-hidden />
              {data.represents ? (
                <span>
                  представляет:{" "}
                  <Link
                    to="/vendors/$vendorId"
                    params={{ vendorId: String(data.represents.id) }}
                    className="underline"
                  >
                    {data.represents.name}
                  </Link>
                </span>
              ) : (
                "самостоятельный бренд"
              )}
            </div>
            <div className="mt-1 text-small text-muted-foreground">
              <InlineEditText
                value={data.note ?? ""}
                ariaLabel="Редактировать примечание"
                multiline
                placeholder="+ примечание"
                displayClassName="text-left hover:text-foreground"
                inputClassName="w-full rounded-md border border-border bg-transparent px-1 py-0.5 text-small outline-none focus-visible:border-ring"
                onSubmit={async (next) => {
                  await updateHeader.mutateAsync({ note: next })
                }}
              />
            </div>
          </div>
          <label className="flex shrink-0 items-center gap-2 text-small text-muted-foreground">
            Соглашение
            <Switch
              checked={data.starred}
              disabled={toggleAgreement.isPending}
              onCheckedChange={(next) => toggleAgreement.mutate(next)}
              aria-label="Соглашение о сотрудничестве"
            />
          </label>
        </div>
      </section>

      {/* Варианты написания */}
      <section className={`${CARD} px-5 py-[15px]`}>
        <div className="mb-2.5 text-caption text-muted-foreground uppercase">
          Варианты написания
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">
              вариантов пока нет
            </span>
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
                className="h-7 rounded-md border border-border bg-transparent px-2 text-small"
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
            <button
              type="button"
              onClick={() => setAliasOpen(true)}
              className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-strong px-2.5 py-1 text-small text-primary"
            >
              <Plus className="size-3" aria-hidden />
              вариант
            </button>
          )}
        </div>
      </section>

      {/* Бренд и объединение */}
      <section className={`${CARD} px-5 py-[15px]`}>
        <div className="mb-2.5 text-caption text-muted-foreground uppercase">
          Бренд и объединение
        </div>
        <div className="flex items-center gap-2.5">
          <Award className="size-4 shrink-0 text-primary" aria-hidden />
          <div className="flex-1 text-small">
            {data.represents ? (
              <>
                Представляет:{" "}
                <Link
                  to="/vendors/$vendorId"
                  params={{ vendorId: String(data.represents.id) }}
                  className="underline"
                >
                  {data.represents.name}
                </Link>
              </>
            ) : (
              <>
                Самостоятельный бренд
                <div className="text-caption text-muted-foreground">
                  {data.represented_count > 0
                    ? `${data.represented_count} ${pluralVendors(
                        data.represented_count
                      )} представляют этот бренд`
                    : "не представляет другого вендора"}
                </div>
              </>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled
            className="gap-1.5"
            title="в разработке"
          >
            <Merge className="size-3.5" aria-hidden />
            Объединить
            <span className="text-caption text-muted-foreground">· скоро</span>
          </Button>
        </div>
      </section>

      {/* Где разрешён */}
      <section className={`${CARD} py-[15px]`}>
        <div className="flex items-baseline justify-between px-5">
          <span className="text-caption text-muted-foreground uppercase">
            Где разрешён
          </span>
          {standards.length > 0 && (
            <span className="text-caption text-muted-foreground">
              {standards.length} {pluralStandards(standards.length)} ·{" "}
              {positionTotal} {pluralPositions(positionTotal)}
            </span>
          )}
        </div>

        {whereAllowed.isPending ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            Загрузка…
          </div>
        ) : whereAllowed.isError ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            Не удалось загрузить
          </div>
        ) : standards.length === 0 ? (
          <div className="mt-2 px-5 text-small text-muted-foreground">
            {WHERE_ALLOWED_EMPTY}
          </div>
        ) : (
          <>
            <Accordion type="multiple" className="mt-2.5">
              {standards.map((s) => {
                const count = `${s.position_count} ${pluralPositions(s.position_count)}`
                const summary = standardAllClasses(s)
                  ? `${count} · все классы`
                  : count
                return (
                  <AccordionItem
                    key={s.building_type_id}
                    value={String(s.building_type_id)}
                    className="border-b-0"
                  >
                    <AccordionPrimitive.Header className="flex">
                      <AccordionPrimitive.Trigger className="group flex w-full items-center gap-2.5 border-y border-border bg-muted px-5 py-2.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <ChevronRight
                          aria-hidden
                          className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 group-data-[state=open]:text-primary"
                        />
                        <span className="flex-1 text-small font-medium">
                          {s.building_type_name}
                        </span>
                        <span className="text-caption text-muted-foreground">
                          {summary}
                        </span>
                      </AccordionPrimitive.Trigger>
                    </AccordionPrimitive.Header>
                    <AccordionContent className="mr-5 ml-8 border-l border-border pl-4">
                      <div className="divide-y divide-border/60">
                        {s.positions.map((p) => (
                          <div
                            key={p.position_id}
                            className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-2"
                          >
                            <span className="flex-1 text-small">
                              {p.position_name}
                            </span>
                            {isAllClasses(p, s.segment_count) ? (
                              <Badge
                                variant="outline"
                                className="text-muted-foreground"
                              >
                                все классы
                              </Badge>
                            ) : (
                              <div className="flex w-full flex-wrap gap-1.5">
                                {p.chips.map((c) =>
                                  c.state === "allowed" ? (
                                    <Badge
                                      key={c.segment_id}
                                      variant="outline"
                                      className="bg-accent"
                                    >
                                      {c.segment_name}
                                    </Badge>
                                  ) : (
                                    <Badge
                                      key={c.segment_id}
                                      variant="outline"
                                      className="border-dashed border-border-strong text-muted-foreground line-through"
                                      title={excludedTooltip(c.release_label)}
                                      aria-label={excludedTooltip(
                                        c.release_label
                                      )}
                                    >
                                      {c.segment_name}
                                    </Badge>
                                  )
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                )
              })}
            </Accordion>
            {hasExcludedChips(standards) ? (
              <p className="mt-3 flex items-center gap-1.5 px-5 text-caption text-muted-foreground">
                <span className="rounded-sm border border-dashed border-border-strong px-1.5 line-through">
                  класс
                </span>
                — был в последнем релизе, исключён · показано текущее состояние
                стандартов
              </p>
            ) : (
              <p className="mt-3 px-5 text-caption text-muted-foreground">
                {whereAllowedLegend()}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  )
}
