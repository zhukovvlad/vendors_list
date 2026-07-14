import { CheckCheck, CircleMinus } from "lucide-react"

import { AddClassPopover } from "./AddClassPopover"
import { ClassChip } from "./ClassChip"
import {
  isAllClasses,
  splitQualifier,
  type Position,
  type Segment,
  type Standard,
} from "./model"

/**
 * Ряд одной позиции в блоке «Где разрешён»: имя (с уточнением в скобках), в edit —
 * `⊖` (исключить позицию) и `×`/«вернуть» на чипах + «+ класс». В view при полном
 * покрытии показывает свёртку «все классы» вместо перечня чипов.
 *
 * Колбэки исключения/возврата/добавления — семантические, приходят из секции
 * (там живут мутации и диалоги). `segments` — от `WhereAllowedStandard` (один
 * `useSegments` на стандарт).
 */
export function PositionRow({
  standard,
  position,
  editMode,
  segments,
  addPending,
  onExcludePosition,
  onExcludeClass,
  onRestore,
  onAddClasses,
}: {
  standard: Standard
  position: Position
  editMode: boolean
  segments: Segment[]
  addPending: boolean
  onExcludePosition: (standard: Standard, position: Position) => void
  onExcludeClass: (positionId: number, segmentId: number) => void
  onRestore: (positionId: number, segmentId: number) => void
  onAddClasses: (positionId: number, segmentIds: number[]) => void
}) {
  const { head, qualifier } = splitQualifier(position.position_name)
  const presentSegmentIds = new Set(position.chips.map((c) => c.segment_id))

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-2">
      <span className="flex-1 text-[15px] tracking-tight text-foreground">
        {head}
        {qualifier && (
          <span className="text-[13px] text-muted-foreground">
            {" "}
            ({qualifier})
          </span>
        )}
      </span>
      {editMode && (
        <button
          type="button"
          aria-label={`исключить из позиции ${position.position_name}`}
          onClick={() => onExcludePosition(standard, position)}
          className="shrink-0 text-muted-foreground hover:text-destructive"
        >
          <CircleMinus className="size-4" aria-hidden />
        </button>
      )}
      {!editMode && isAllClasses(position, standard.segment_count) ? (
        <span className="flex items-center gap-1 text-caption text-muted-foreground">
          <CheckCheck className="size-3.5 text-mint" aria-hidden />
          все классы
        </span>
      ) : (
        <div className="flex w-full flex-wrap items-center gap-1.5">
          {position.chips.map((c) => (
            <ClassChip
              key={c.segment_id}
              chip={c}
              editMode={editMode}
              onExclude={() =>
                onExcludeClass(position.position_id, c.segment_id)
              }
              onRestore={() => onRestore(position.position_id, c.segment_id)}
            />
          ))}
          {editMode && (
            <AddClassPopover
              segments={segments}
              presentSegmentIds={presentSegmentIds}
              pending={addPending}
              onAdd={(segmentIds) =>
                onAddClasses(position.position_id, segmentIds)
              }
            />
          )}
        </div>
      )}
    </div>
  )
}
