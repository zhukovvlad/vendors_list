import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { Award, Check, Merge, Pencil, Star } from "lucide-react"

import {
  useBuildingTypes,
  useToggleAgreement,
  useUpdateVendorHeader,
  useVendor,
  useVendorWhereAllowed,
} from "@/api/queries"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import { InlineEditText } from "./InlineEditText"
import { VendorAliasesSection } from "./VendorAliasesSection"
import { WhereAllowedSection } from "./WhereAllowedSection"
import {
  avatarInitial,
  CARD,
  KIND_LABELS,
  kindLabel,
  pluralVendors,
} from "./model"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)
  // Read-запросы «где разрешён» стартуют здесь (параллельно с useVendor), а не в
  // секции: та под early-return загрузки вендора — иначе запросы шли бы водопадом.
  const whereAllowed = useVendorWhereAllowed(id)
  const buildingTypes = useBuildingTypes()
  const toggleAgreement = useToggleAgreement(id)
  const updateHeader = useUpdateVendorHeader(id)
  const [nameError, setNameError] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  // Секции «Где разрешён» в edit раскрыты по умолчанию — храним лишь то, что
  // пользователь ЯВНО свернул (сама секция выводит «раскрыто» из данных). Сброс
  // при входе в правку — синхронно в обработчике кнопки ниже, без seed-эффекта.
  const [collapsed, setCollapsed] = useState<string[]>([])

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
            // Новая сессия правки — сбрасываем свёрнутое (все секции раскрыты).
            if (!editMode) setCollapsed([])
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
      <VendorAliasesSection
        id={id}
        aliases={data.aliases}
        editMode={editMode}
      />

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

      <WhereAllowedSection
        id={id}
        editMode={editMode}
        collapsed={collapsed}
        onCollapsedChange={setCollapsed}
        whereAllowed={whereAllowed}
        buildingTypes={buildingTypes}
      />
    </div>
  )
}
