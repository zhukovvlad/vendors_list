import { useState, type ReactNode } from "react"
import { Link } from "@tanstack/react-router"
import { Accordion as AccordionPrimitive } from "radix-ui"
import { toast } from "sonner"
import {
  Award,
  Check,
  CheckCheck,
  ChevronRight,
  CircleMinus,
  Ellipsis,
  Merge,
  Pencil,
  Plus,
  Star,
  X,
} from "lucide-react"

import {
  useAddAlias,
  useAddListings,
  useBuildingTypes,
  useExcludeListings,
  useRemoveAlias,
  useRestoreListing,
  useSegments,
  useToggleAgreement,
  useUpdateVendorHeader,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import { Accordion, AccordionItem } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { vendorCardRoute } from "@/router"

import { AddStandardDialog } from "./AddStandardDialog"
import { ExcludeDialog } from "./ExcludeDialog"
import { InlineEditText } from "./InlineEditText"
import {
  avatarInitial,
  excludedTooltip,
  excludeScaleForPosition,
  excludeScaleForStandard,
  hasExcludedChips,
  isAllClasses,
  KIND_LABELS,
  kindLabel,
  pluralClasses,
  pluralPositions,
  pluralStandards,
  pluralVendors,
  splitQualifier,
  standardAllClasses,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
} from "./model"

const CARD = "rounded-xl border border-border bg-card"

type ExcludeBody = {
  scope: "class" | "position" | "standard"
  position_id?: number
  segment_id?: number
  building_type_id?: number
}

type ExcludeDialogState = {
  title: string
  scale: { positions: number; classes: number }
  body: ExcludeBody
}

/**
 * Контент секции «Где разрешён». Аналог DS `AccordionContent`, но с оглядкой на
 * edit-режим (вариант B фикса клиппинга): в правке секции раскрыты принудительно
 * и контент РАСТЁТ (чипы получают ×, появляются ⊖/«+ класс»). Radix замеряет
 * `--radix-accordion-content-height` в момент открытия — до дорастания, — и
 * `overflow-hidden` режет хвост. Поэтому в edit рендерим без анимации/overflow/
 * фикс-высоты (height auto, overflow visible). В view контент статичен — анимация
 * и клип остаются как в DS. DS-примитив не форкаем (golden-rule: правка на уровне
 * экрана, триггер здесь тоже кастомный).
 */
function WhereAllowedContent({
  editMode,
  className,
  children,
}: {
  editMode: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <AccordionPrimitive.Content
      data-slot="accordion-content"
      className={cn(
        "text-sm",
        !editMode &&
          "overflow-hidden data-open:animate-accordion-down data-closed:animate-accordion-up"
      )}
    >
      <div
        className={cn(
          "pt-0 pb-2.5",
          !editMode && "h-(--radix-accordion-content-height)",
          className
        )}
      >
        {children}
      </div>
    </AccordionPrimitive.Content>
  )
}

/**
 * «+ класс» на конце ряда позиции: Popover со списком сегментов типа, которых
 * ещё нет среди чипов позиции (ни allowed, ни excluded). Каждый экземпляр — свой
 * `useSegments` (хук в компоненте, не в цикле рендера родителя — валидно per instance).
 */
function AddClassPopover({
  buildingTypeId,
  presentSegmentIds,
  pending,
  onAdd,
}: {
  buildingTypeId: number
  presentSegmentIds: Set<number>
  pending: boolean
  onAdd: (segmentIds: number[]) => void
}) {
  const segments = useSegments(buildingTypeId)
  const [open, setOpen] = useState(false)
  const [checked, setChecked] = useState<number[]>([])
  const missing = (segments.data ?? []).filter(
    (s) => !presentSegmentIds.has(s.id)
  )

  if (missing.length === 0) return null

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setChecked([])
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-strong px-2 py-0.5 text-caption text-primary"
        >
          <Plus className="size-3" aria-hidden />
          класс
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56">
        <div className="flex flex-col gap-1.5">
          {missing.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-small">
              <Checkbox
                checked={checked.includes(s.id)}
                onCheckedChange={(next) =>
                  setChecked((prev) =>
                    next === true
                      ? [...prev, s.id]
                      : prev.filter((id) => id !== s.id)
                  )
                }
              />
              {s.name}
            </label>
          ))}
        </div>
        <Button
          size="sm"
          disabled={checked.length === 0 || pending}
          onClick={() => {
            onAdd(checked)
            setChecked([])
            setOpen(false)
          }}
        >
          Добавить
        </Button>
      </PopoverContent>
    </Popover>
  )
}

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)
  const whereAllowed = useVendorWhereAllowed(id)
  const toggleAgreement = useToggleAgreement(id)
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const updateHeader = useUpdateVendorHeader(id)
  const addListings = useAddListings(id)
  const excludeListings = useExcludeListings(id)
  const restoreListing = useRestoreListing(id)
  const buildingTypes = useBuildingTypes()
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")
  const [nameError, setNameError] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [expanded, setExpanded] = useState<string[]>([])
  const [excludeDialog, setExcludeDialog] = useState<ExcludeDialogState | null>(
    null
  )
  const [addStandardOpen, setAddStandardOpen] = useState(false)

  /**
   * Исключение с фидбэком: тост фактического масштаба на успехе (гард на нули —
   * гонка/no-op тоста не даёт), тост ошибки на отказе (409/сеть). Возвращает
   * true при успехе — вызыватель-диалог закрывается только тогда.
   */
  async function confirmExclude(body: ExcludeBody): Promise<boolean> {
    try {
      const res = await excludeListings.mutateAsync(body)
      if (res && res.excluded_classes > 0) {
        toast(
          `Исключён из ${res.excluded_positions} ${pluralPositions(
            res.excluded_positions
          )} и ${res.excluded_classes} ${pluralClasses(res.excluded_classes)}`
        )
      }
      return true
    } catch {
      toast("Не удалось исключить — попробуйте ещё раз")
      return false
    }
  }

  /** Закрывает диалог только при успехе; на отказе (409/сеть) — тост и диалог
   * остаётся открытым, чтобы можно было повторить попытку. */
  async function confirmAddStandard(body: {
    position_id: number
    segment_ids: number[]
  }) {
    try {
      await addListings.mutateAsync(body)
      setAddStandardOpen(false)
    } catch {
      toast("Не удалось добавить стандарт — попробуйте ещё раз")
    }
  }

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
  const presentStandards = new Set(standards.map((s) => s.building_type_id))
  const allStandardsPresent =
    (buildingTypes.data?.length ?? 0) > 0 &&
    presentStandards.size >= (buildingTypes.data?.length ?? 0)

  // «+ стандарт» — действие блока; по макету идёт ВЫШЕ легенды (легенда закрывает
  // блок последней). Один элемент переиспользуется в пустом и непустом состоянии.
  const plusStandardEl = (
    <div className="mt-3 px-5">
      <button
        type="button"
        disabled={allStandardsPresent}
        title={
          allStandardsPresent ? "вендор есть во всех стандартах" : undefined
        }
        onClick={() => setAddStandardOpen(true)}
        className="inline-flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border-strong px-2.5 py-1.5 text-small text-primary disabled:cursor-not-allowed disabled:opacity-40"
      >
        + стандарт
      </button>
    </div>
  )

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-3 py-6">
      <div className="flex items-center justify-between">
        <span className="text-caption text-muted-foreground uppercase">
          Вендор
        </span>
        <Button
          variant={editMode ? "default" : "outline"}
          size="sm"
          className="gap-1.5"
          onClick={() => {
            if (!editMode)
              setExpanded(standards.map((s) => String(s.building_type_id)))
            setEditMode((v) => !v)
          }}
        >
          {editMode ? (
            <Check className="size-3.5" aria-hidden />
          ) : (
            <Pencil className="size-3.5" aria-hidden />
          )}
          {editMode ? "Готово" : "Редактировать"}
        </Button>
      </div>
      {editMode && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5 text-caption text-muted-foreground">
          Свойства вендора сохраняются сразу · правки разрешений применяются
          немедленно и войдут в следующий релиз (текущие релизы не
          затрагиваются)
        </div>
      )}
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
                  readOnly={!editMode}
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
              {editMode ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button type="button" aria-label="Изменить тип вендора">
                      <Badge
                        variant="outline"
                        className="cursor-pointer rounded-full hover:border-primary"
                      >
                        {kindLabel(data.kind)}
                      </Badge>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    {Object.entries(KIND_LABELS).map(([value, label]) => (
                      <DropdownMenuItem
                        key={value}
                        onSelect={() => updateHeader.mutate({ kind: value })}
                      >
                        {label}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Badge variant="outline" className="rounded-full">
                  {kindLabel(data.kind)}
                </Badge>
              )}
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
                readOnly={!editMode}
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
              disabled={!editMode || toggleAgreement.isPending}
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
              {editMode && (
                <button
                  type="button"
                  aria-label={`удалить ${a.alias}`}
                  onClick={() => removeAlias.mutate(a.id)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3" />
                </button>
              )}
            </Badge>
          ))}
          {editMode &&
            (aliasOpen ? (
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
            ))}
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
          {editMode && (
            <Button
              variant="outline"
              size="sm"
              disabled
              className="gap-1.5"
              title="в разработке"
            >
              <Merge className="size-3.5" aria-hidden />
              Объединить
              <span className="text-caption text-muted-foreground">
                · скоро
              </span>
            </Button>
          )}
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
          <>
            <div className="mt-2 px-5 text-small text-muted-foreground">
              {WHERE_ALLOWED_EMPTY}
            </div>
            {editMode && plusStandardEl}
          </>
        ) : (
          <>
            <Accordion
              type="multiple"
              className="mt-2.5"
              {...(editMode
                ? { value: expanded, onValueChange: setExpanded }
                : {})}
            >
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
                    <AccordionPrimitive.Header className="flex border-y border-border bg-muted">
                      <AccordionPrimitive.Trigger className="group flex flex-1 items-center gap-2.5 px-5 py-2.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <ChevronRight
                          aria-hidden
                          className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 group-data-[state=open]:text-primary"
                        />
                        <span className="flex-1 text-caption font-medium tracking-[0.09em] text-muted-foreground uppercase group-data-[state=open]:text-foreground">
                          {s.building_type_name}
                        </span>
                        {/* Счётчик/сводка — атрибут просмотра: в edit полоса растёт
                            в чипы, а сводка полуправдива и конкурирует с кебабом. */}
                        {!editMode && (
                          <span className="text-caption text-muted-foreground">
                            {summary}
                          </span>
                        )}
                      </AccordionPrimitive.Trigger>
                      {editMode && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              aria-label={`действия стандарта ${s.building_type_name}`}
                              className="flex shrink-0 items-center px-3 text-muted-foreground hover:text-foreground"
                            >
                              <Ellipsis className="size-4" aria-hidden />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() =>
                                setExcludeDialog({
                                  title: `Исключить из «${s.building_type_name}»?`,
                                  scale: excludeScaleForStandard(s),
                                  body: {
                                    scope: "standard",
                                    building_type_id: s.building_type_id,
                                  },
                                })
                              }
                            >
                              Исключить из стандарта
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </AccordionPrimitive.Header>
                    <WhereAllowedContent
                      editMode={editMode}
                      className="mr-5 ml-8 border-l border-border pl-4"
                    >
                      <div className="divide-y divide-border/60">
                        {s.positions.map((p) => {
                          const presentSegmentIds = new Set(
                            p.chips.map((c) => c.segment_id)
                          )
                          return (
                            <div
                              key={p.position_id}
                              className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-2"
                            >
                              <span className="flex-1 text-[15px] tracking-tight text-foreground">
                                {(() => {
                                  const { head, qualifier } = splitQualifier(
                                    p.position_name
                                  )
                                  return (
                                    <>
                                      {head}
                                      {qualifier && (
                                        <span className="text-[13px] text-muted-foreground">
                                          {" "}
                                          ({qualifier})
                                        </span>
                                      )}
                                    </>
                                  )
                                })()}
                              </span>
                              {editMode && (
                                <button
                                  type="button"
                                  aria-label={`исключить из позиции ${p.position_name}`}
                                  onClick={() =>
                                    setExcludeDialog({
                                      title: `Исключить «${splitQualifier(p.position_name).head}» из «${s.building_type_name}»?`,
                                      scale: excludeScaleForPosition(p),
                                      body: {
                                        scope: "position",
                                        position_id: p.position_id,
                                        building_type_id: s.building_type_id,
                                      },
                                    })
                                  }
                                  className="shrink-0 text-muted-foreground hover:text-destructive"
                                >
                                  <CircleMinus className="size-4" aria-hidden />
                                </button>
                              )}
                              {!editMode && isAllClasses(p, s.segment_count) ? (
                                <span className="flex items-center gap-1 text-caption text-muted-foreground">
                                  <CheckCheck
                                    className="size-3.5 text-mint"
                                    aria-hidden
                                  />
                                  все классы
                                </span>
                              ) : (
                                <div className="flex w-full flex-wrap items-center gap-1.5">
                                  {p.chips.map((c) =>
                                    c.state === "allowed" ? (
                                      <span
                                        key={c.segment_id}
                                        className="inline-flex items-center gap-1"
                                      >
                                        <Badge
                                          variant="outline"
                                          className="bg-accent"
                                        >
                                          {c.segment_name}
                                        </Badge>
                                        {editMode && (
                                          <button
                                            type="button"
                                            aria-label={`исключить класс ${c.segment_name}`}
                                            onClick={() => {
                                              void confirmExclude({
                                                scope: "class",
                                                position_id: p.position_id,
                                                segment_id: c.segment_id,
                                              })
                                            }}
                                            className="text-muted-foreground hover:text-destructive"
                                          >
                                            <X className="size-3" />
                                          </button>
                                        )}
                                      </span>
                                    ) : (
                                      <span
                                        key={c.segment_id}
                                        className="inline-flex items-center gap-1.5"
                                      >
                                        <Badge
                                          variant="outline"
                                          className="border-dashed border-border-strong text-muted-foreground line-through"
                                          title={excludedTooltip(
                                            c.release_label
                                          )}
                                          aria-label={excludedTooltip(
                                            c.release_label
                                          )}
                                        >
                                          {c.segment_name}
                                        </Badge>
                                        {editMode && (
                                          <button
                                            type="button"
                                            aria-label={`вернуть ${c.segment_name}`}
                                            onClick={() =>
                                              restoreListing.mutate(
                                                {
                                                  position_id: p.position_id,
                                                  segment_id: c.segment_id,
                                                },
                                                {
                                                  onError: () =>
                                                    toast(
                                                      "Не удалось вернуть — попробуйте ещё раз"
                                                    ),
                                                }
                                              )
                                            }
                                            className="text-caption text-primary hover:underline"
                                          >
                                            вернуть
                                          </button>
                                        )}
                                      </span>
                                    )
                                  )}
                                  {editMode && (
                                    <AddClassPopover
                                      buildingTypeId={s.building_type_id}
                                      presentSegmentIds={presentSegmentIds}
                                      pending={addListings.isPending}
                                      onAdd={(segmentIds) =>
                                        addListings.mutate(
                                          {
                                            position_id: p.position_id,
                                            segment_ids: segmentIds,
                                          },
                                          {
                                            onError: () =>
                                              toast(
                                                "Не удалось добавить класс — попробуйте ещё раз"
                                              ),
                                          }
                                        )
                                      }
                                    />
                                  )}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </WhereAllowedContent>
                  </AccordionItem>
                )
              })}
            </Accordion>
            {editMode && plusStandardEl}
            {hasExcludedChips(standards) ? (
              <p className="mt-3 flex items-center gap-1.5 px-5 text-caption text-muted-foreground">
                <span className="rounded-sm border border-dashed border-border-strong px-1.5 line-through">
                  класс
                </span>
                — исключён, войдёт в следующий релиз · {whereAllowedLegend()}
              </p>
            ) : (
              <p className="mt-3 px-5 text-caption text-muted-foreground">
                {whereAllowedLegend()}
              </p>
            )}
          </>
        )}
      </section>
      <AddStandardDialog
        open={addStandardOpen}
        onOpenChange={setAddStandardOpen}
        present={presentStandards}
        pending={addListings.isPending}
        onAdd={confirmAddStandard}
      />
      <ExcludeDialog
        open={excludeDialog !== null}
        onOpenChange={(open) => {
          if (!open) setExcludeDialog(null)
        }}
        title={excludeDialog?.title ?? ""}
        scale={excludeDialog?.scale ?? { positions: 0, classes: 0 }}
        pending={excludeListings.isPending}
        onConfirm={() => {
          if (!excludeDialog) return
          // Закрываем диалог ТОЛЬКО при успехе — на отказе (409/сеть)
          // confirmExclude показал тост, диалог остаётся для повтора.
          void confirmExclude(excludeDialog.body).then((ok) => {
            if (ok) setExcludeDialog(null)
          })
        }}
      />
    </div>
  )
}
