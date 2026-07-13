import { useState } from "react"

import { useBuildingTypes, useMetaPositions, useSegments } from "@/api/queries"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"

interface AddStandardDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Стандарты (building_type_id), где вендор уже присутствует — из where-allowed. */
  present: Set<number>
  pending: boolean
  onAdd: (body: { position_id: number; segment_ids: number[] }) => void
}

/**
 * Диалог «+ стандарт»: три шага в одном Dialog — стандарт (RadioGroup, стандарты
 * из `present` приглушены и помечены «уже присутствует») → позиция (Command-комбобокс
 * с серверным поиском через `useMetaPositions`) → классы (Checkbox по `useSegments`;
 * одноклассовый тип типа объекта — единственный чекбокс всегда отмечен).
 *
 * Экземпляр Dialog стабилен (без `key`-ремаунта — иначе ломается exit-анимация
 * Radix). Шаговое состояние сбрасывается в `handleOpenChange` — обработчике
 * события закрытия (Cancel/Esc/оверлей), не в эффекте (react-hooks/set-state-in-effect
 * этого не запрещает для обработчиков событий). Родительский `onOpenChange`
 * при этом всё равно вызывается — родитель остаётся источником истины для `open`
 * (успешный `onAdd` закрывает диалог сам, минуя этот обработчик).
 */
export function AddStandardDialog({
  open,
  onOpenChange,
  present,
  pending,
  onAdd,
}: AddStandardDialogProps) {
  const buildingTypes = useBuildingTypes()
  const [buildingTypeId, setBuildingTypeId] = useState<number | null>(null)
  const [q, setQ] = useState("")
  const positions = useMetaPositions(
    buildingTypeId ?? undefined,
    q || undefined
  )
  const [positionId, setPositionId] = useState<number | null>(null)
  const [positionName, setPositionName] = useState("")
  const segments = useSegments(buildingTypeId ?? undefined)
  const [segmentIds, setSegmentIds] = useState<number[]>([])

  const singleSegment =
    (segments.data?.length ?? 0) === 1 ? segments.data![0] : null

  const canSubmit =
    positionId !== null &&
    (singleSegment !== null ? true : segmentIds.length > 0) &&
    !pending

  function selectBuildingType(id: number) {
    setBuildingTypeId(id)
    setPositionId(null)
    setPositionName("")
    setSegmentIds([])
  }

  function handleAdd() {
    if (positionId === null) return
    const finalSegmentIds = singleSegment ? [singleSegment.id] : segmentIds
    onAdd({ position_id: positionId, segment_ids: finalSegmentIds })
  }

  /** Сброс шагового состояния на закрытие (Cancel/Esc/оверлей); родитель уведомляется всегда. */
  function handleOpenChange(next: boolean) {
    if (!next) {
      setBuildingTypeId(null)
      setQ("")
      setPositionId(null)
      setPositionName("")
      setSegmentIds([])
    }
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>+ стандарт</DialogTitle>
          <DialogDescription>
            появится в выбранной позиции; запись применится сразу и войдёт в
            следующий релиз
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div>
            <div className="mb-1.5 text-caption text-muted-foreground uppercase">
              Стандарт
            </div>
            <RadioGroup
              value={buildingTypeId !== null ? String(buildingTypeId) : ""}
              onValueChange={(v) => selectBuildingType(Number(v))}
            >
              {(buildingTypes.data ?? []).map((bt) => {
                const isPresent = present.has(bt.id)
                return (
                  <label
                    key={bt.id}
                    className="flex items-center gap-2 text-small aria-disabled:opacity-50"
                    aria-disabled={isPresent}
                  >
                    <RadioGroupItem
                      value={String(bt.id)}
                      disabled={isPresent}
                    />
                    {bt.name}
                    {isPresent && (
                      <span className="text-caption text-muted-foreground">
                        уже присутствует
                      </span>
                    )}
                  </label>
                )
              })}
            </RadioGroup>
          </div>

          {buildingTypeId !== null && (
            <div>
              <div className="mb-1.5 text-caption text-muted-foreground uppercase">
                Позиция
              </div>
              <Command
                shouldFilter={false}
                className="rounded-lg border border-border"
              >
                <CommandInput
                  value={q}
                  onValueChange={setQ}
                  placeholder="поиск позиции…"
                />
                <CommandList>
                  {positions.isPending ? (
                    <CommandEmpty>Загрузка…</CommandEmpty>
                  ) : (positions.data ?? []).length === 0 ? (
                    <CommandEmpty>Ничего не найдено</CommandEmpty>
                  ) : (
                    <CommandGroup>
                      {(positions.data ?? []).map((p) => (
                        <CommandItem
                          key={p.id}
                          value={String(p.id)}
                          data-checked={positionId === p.id}
                          onSelect={() => {
                            setPositionId(p.id)
                            setPositionName(p.name)
                          }}
                        >
                          {p.name}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  )}
                </CommandList>
              </Command>
              {positionId !== null && (
                <div className="mt-1.5 text-caption text-muted-foreground">
                  выбрано: {positionName}
                </div>
              )}
            </div>
          )}

          {buildingTypeId !== null && positionId !== null && (
            <div>
              <div className="mb-1.5 text-caption text-muted-foreground uppercase">
                Классы
              </div>
              {segments.isPending ? (
                <div className="text-small text-muted-foreground">
                  Загрузка…
                </div>
              ) : singleSegment ? (
                <div className="flex items-center gap-2 text-small">
                  <Checkbox checked disabled />
                  {singleSegment.name}
                  <span className="text-caption text-muted-foreground">
                    у этого типа один класс
                  </span>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {(segments.data ?? []).map((s) => (
                    <label
                      key={s.id}
                      className="flex items-center gap-2 text-small"
                    >
                      <Checkbox
                        checked={segmentIds.includes(s.id)}
                        onCheckedChange={(next) =>
                          setSegmentIds((prev) =>
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
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={!canSubmit} onClick={handleAdd}>
            Добавить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
