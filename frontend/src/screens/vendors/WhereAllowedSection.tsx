import { useState } from "react"
import { toast } from "sonner"

import {
  useAddListings,
  useBuildingTypes,
  useExcludeListings,
  useRestoreListing,
  useVendorWhereAllowed,
} from "@/api/queries"
import { Accordion } from "@/components/ui/accordion"

import { AddStandardDialog } from "./AddStandardDialog"
import { ExcludeDialog } from "./ExcludeDialog"
import { WhereAllowedStandard } from "./WhereAllowedStandard"
import {
  CARD,
  excludeScaleForPosition,
  excludeScaleForStandard,
  hasExcludedChips,
  pluralClasses,
  pluralPositions,
  pluralStandards,
  splitQualifier,
  WHERE_ALLOWED_EMPTY,
  whereAllowedLegend,
  type Position,
  type Standard,
} from "./model"

// Read-запросы приходят пропами из экрана (параллельный старт с useVendor) —
// типы деривим из хуков, чтобы контракт следовал за сгенерированной схемой.
type WhereAllowedQuery = ReturnType<typeof useVendorWhereAllowed>
type BuildingTypesQuery = ReturnType<typeof useBuildingTypes>

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
 * Блок «Где разрешён» карточки вендора: обратный индекс разрешений (стандарт →
 * позиция → классы) плюс операции правки в edit-режиме. Владеет мутациями и
 * диалогами; рендер разложен на `WhereAllowedStandard` → `PositionRow` → `ClassChip`.
 * Вниз идут семантические колбэки (исключить/вернуть/добавить) — сами мутации и
 * построение диалогов остаются здесь, единым местом.
 *
 * Read-запросы (`whereAllowed`/`buildingTypes`) приходят пропами из экрана-контейнера
 * — так они стартуют ПАРАЛЛЕЛЬНО с `useVendor` на входе, а не водопадом после того,
 * как секция смонтируется (секция под early-return загрузки вендора). Мутации —
 * хуки здесь (сеть только по действию, тайминг маунта не важен).
 *
 * `collapsed` живёт в родителе (сброс раскрытия синхронен со входом в edit —
 * обработчик кнопки режима, без seed-эффекта): в edit раскрыто = все секции минус
 * явно свёрнутые (производно от данных, устойчиво к ещё не пришедшим стандартам).
 */
export function WhereAllowedSection({
  id,
  editMode,
  collapsed,
  onCollapsedChange,
  whereAllowed,
  buildingTypes,
}: {
  id: number
  editMode: boolean
  collapsed: string[]
  onCollapsedChange: (next: string[]) => void
  whereAllowed: WhereAllowedQuery
  buildingTypes: BuildingTypesQuery
}) {
  const addListings = useAddListings(id)
  const excludeListings = useExcludeListings(id)
  const restoreListing = useRestoreListing(id)
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

  // Семантические колбэки для под-компонентов: построение диалога/мутации — здесь.
  function onExcludeStandard(s: Standard) {
    setExcludeDialog({
      title: `Исключить из «${s.building_type_name}»?`,
      scale: excludeScaleForStandard(s),
      body: { scope: "standard", building_type_id: s.building_type_id },
    })
  }

  function onExcludePosition(s: Standard, p: Position) {
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

  function onExcludeClass(positionId: number, segmentId: number) {
    void confirmExclude({
      scope: "class",
      position_id: positionId,
      segment_id: segmentId,
    })
  }

  function onRestore(positionId: number, segmentId: number) {
    restoreListing.mutate(
      { position_id: positionId, segment_id: segmentId },
      { onError: () => toast("Не удалось вернуть — попробуйте ещё раз") }
    )
  }

  function onAddClasses(positionId: number, segmentIds: number[]) {
    addListings.mutate(
      { position_id: positionId, segment_ids: segmentIds },
      { onError: () => toast("Не удалось добавить класс — попробуйте ещё раз") }
    )
  }

  const standards = whereAllowed.data?.standards ?? []
  const allStandardIds = standards.map((s) => String(s.building_type_id))
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
    <>
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
                ? {
                    // Раскрыто = все секции минус явно свёрнутые (производно от данных).
                    value: allStandardIds.filter((v) => !collapsed.includes(v)),
                    onValueChange: (open: string[]) =>
                      onCollapsedChange(
                        allStandardIds.filter((v) => !open.includes(v))
                      ),
                  }
                : {})}
            >
              {standards.map((s) => (
                <WhereAllowedStandard
                  key={s.building_type_id}
                  standard={s}
                  editMode={editMode}
                  addPending={addListings.isPending}
                  onExcludeStandard={onExcludeStandard}
                  onExcludePosition={onExcludePosition}
                  onExcludeClass={onExcludeClass}
                  onRestore={onRestore}
                  onAddClasses={onAddClasses}
                />
              ))}
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
    </>
  )
}
