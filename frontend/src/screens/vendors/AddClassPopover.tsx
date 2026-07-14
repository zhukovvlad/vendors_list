import { useState } from "react"
import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

import type { Segment } from "./model"

/**
 * «+ класс» на конце ряда позиции: Popover со списком сегментов типа, которых
 * ещё нет среди чипов позиции (ни allowed, ни excluded). `segments` приходят
 * пропом — их грузит `WhereAllowedStandard` ОДНИМ `useSegments` на стандарт, а не
 * каждый ряд своим хуком (иначе N observer'ов на один стандарт).
 */
export function AddClassPopover({
  segments,
  presentSegmentIds,
  pending,
  onAdd,
}: {
  segments: Segment[]
  presentSegmentIds: Set<number>
  pending: boolean
  onAdd: (segmentIds: number[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [checked, setChecked] = useState<number[]>([])
  const missing = segments.filter((s) => !presentSegmentIds.has(s.id))

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
