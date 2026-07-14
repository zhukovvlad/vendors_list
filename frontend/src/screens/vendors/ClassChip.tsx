import { X } from "lucide-react"

import { Badge } from "@/components/ui/badge"

import { excludedTooltip, type Chip } from "./model"

/**
 * Чип класса в ряду позиции. `allowed` — приглушённый бейдж с `×` (исключить) в
 * edit; `excluded` — пунктирный зачёркнутый с тултипом релиза и «вернуть» в edit.
 * Колбэки уже связаны родителем с конкретной позицией/сегментом (чип презентационен).
 */
export function ClassChip({
  chip,
  editMode,
  onExclude,
  onRestore,
}: {
  chip: Chip
  editMode: boolean
  onExclude: () => void
  onRestore: () => void
}) {
  if (chip.state === "allowed") {
    return (
      <span className="inline-flex items-center gap-1">
        <Badge
          variant="outline"
          className="bg-accent text-[11px] font-normal text-muted-foreground"
        >
          {chip.segment_name}
        </Badge>
        {editMode && (
          <button
            type="button"
            aria-label={`исключить класс ${chip.segment_name}`}
            onClick={onExclude}
            className="text-muted-foreground hover:text-destructive"
          >
            <X className="size-3" />
          </button>
        )}
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge
        variant="outline"
        className="border-dashed border-border-strong text-[11px] font-normal text-muted-foreground line-through"
        title={excludedTooltip(chip.release_label)}
        aria-label={excludedTooltip(chip.release_label)}
      >
        {chip.segment_name}
      </Badge>
      {editMode && (
        <button
          type="button"
          aria-label={`вернуть ${chip.segment_name}`}
          onClick={onRestore}
          className="text-caption text-primary hover:underline"
        >
          вернуть
        </button>
      )}
    </span>
  )
}
