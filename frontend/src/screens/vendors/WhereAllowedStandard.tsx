import { type ReactNode } from "react"
import { Accordion as AccordionPrimitive } from "radix-ui"
import { ChevronRight, Ellipsis } from "lucide-react"

import { useSegments } from "@/api/queries"
import { AccordionItem } from "@/components/ui/accordion"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

import { PositionRow } from "./PositionRow"
import {
  pluralPositions,
  standardAllClasses,
  type Position,
  type Standard,
} from "./model"

/**
 * Контент секции «Где разрешён». Аналог DS `AccordionContent`, но с оглядкой на
 * edit-режим (вариант B фикса клиппинга): в правке секции раскрыты принудительно
 * и контент РАСТЁТ (чипы получают ×, появляются ⊖/«+ класс»). Radix замеряет
 * `--radix-accordion-content-height` в момент открытия — до дорастания, — и
 * `overflow-hidden` режет хвост. Поэтому в edit рендерим без анимации/overflow
 * (height auto, overflow visible). В view контент статичен — анимация и клип
 * остаются как в DS. DS-примитив не форкаем (golden-rule: правка на уровне
 * экрана, триггер здесь тоже кастомный).
 *
 * Внутренний div НЕ пиннится к `h-(--radix-accordion-content-height)` (в отличие
 * от DS): у нас контент меняет высоту при edit↔view, пока секция раскрыта. Пин
 * замкнул бы петлю с ResizeObserver'ом Radix — на возврате из edit div остаётся
 * растянут под БÓЛЬШУЮ (edit) высоту, observer меряет растянутый div, переменная
 * застревает → лишний отступ снизу. Натуральная высота меряется верно; переменная
 * нужна лишь keyframe-анимации открытия/закрытия, которая работает и без пина.
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
      <div className={cn("pt-0 pb-2.5", className)}>{children}</div>
    </AccordionPrimitive.Content>
  )
}

/**
 * Один стандарт (тип объекта) в блоке «Где разрешён»: заголовок-аккордеон + ряды
 * позиций. Владеет ЕДИНСТВЕННЫМ `useSegments` на стандарт (не по хуку на ряд) —
 * газируется `enabled` через `editMode && isOpen`: в view сегменты не грузятся, а
 * у свёрнутого стандарта запрос неактивен (хук живёт НАД `Accordion.Content`,
 * который анмаунтит содержимое при сворачивании, — сам он так не деактивируется,
 * поэтому гейт по `isOpen` явный). Рендерит `AccordionItem` (контекст `Accordion`
 * — у секции-родителя).
 */
export function WhereAllowedStandard({
  standard,
  editMode,
  isOpen,
  addPending,
  onExcludeStandard,
  onExcludePosition,
  onExcludeClass,
  onRestore,
  onAddClasses,
}: {
  standard: Standard
  editMode: boolean
  isOpen: boolean
  addPending: boolean
  onExcludeStandard: (standard: Standard) => void
  onExcludePosition: (standard: Standard, position: Position) => void
  onExcludeClass: (positionId: number, segmentId: number) => void
  onRestore: (positionId: number, segmentId: number) => void
  onAddClasses: (positionId: number, segmentIds: number[]) => void
}) {
  // Один запрос сегментов на стандарт, только в правке и когда раскрыт.
  const segments = useSegments(
    editMode && isOpen ? standard.building_type_id : undefined
  )

  const count = `${standard.position_count} ${pluralPositions(standard.position_count)}`
  const summary = standardAllClasses(standard) ? `${count} · все классы` : count

  return (
    <AccordionItem
      value={String(standard.building_type_id)}
      className="border-b-0"
    >
      <AccordionPrimitive.Header className="flex border-y border-border bg-muted">
        <AccordionPrimitive.Trigger className="group flex flex-1 items-center gap-2.5 px-5 py-2.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring">
          <ChevronRight
            aria-hidden
            className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 group-data-[state=open]:text-primary"
          />
          <span className="flex-1 text-caption font-medium tracking-[0.09em] text-muted-foreground/70 uppercase group-data-[state=open]:text-muted-foreground">
            {standard.building_type_name}
          </span>
          {/* Счётчик/сводка — атрибут просмотра: в edit полоса растёт в чипы, а
              сводка полуправдива и конкурирует с кебабом. */}
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
                aria-label={`действия стандарта ${standard.building_type_name}`}
                className="flex shrink-0 items-center px-3 text-muted-foreground hover:text-foreground"
              >
                <Ellipsis className="size-4" aria-hidden />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => onExcludeStandard(standard)}
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
          {standard.positions.map((p) => (
            <PositionRow
              key={p.position_id}
              standard={standard}
              position={p}
              editMode={editMode}
              segments={segments.data ?? []}
              addPending={addPending}
              onExcludePosition={onExcludePosition}
              onExcludeClass={onExcludeClass}
              onRestore={onRestore}
              onAddClasses={onAddClasses}
            />
          ))}
        </div>
      </WhereAllowedContent>
    </AccordionItem>
  )
}
