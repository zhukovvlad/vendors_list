/** Чистые хелперы карточки вендора: локализация enum и тексты (без версий релиза). */

const KIND_LABELS: Record<string, string> = {
  manufacturer: "производитель",
  supplier: "поставщик",
  other: "прочее",
}

/** Локализованное имя типа вендора; неизвестное значение — как есть. */
export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind
}

/** Тултип зачёркнутого чипа: релиз идентифицируется label, не номером версии. */
export function excludedTooltip(releaseLabel: string | null): string {
  return releaseLabel
    ? `Был в релизе «${releaseLabel}», исключён в текущем черновике`
    : "Был в последнем релизе, исключён в текущем черновике"
}

/** Пометка пустого обратного индекса: вендор нигде не разрешён сейчас. */
export const WHERE_ALLOWED_EMPTY = "нигде не разрешён"

type ChipLike = { state: string }
type PositionLike = { chips: ChipLike[] }
type StandardLike = { positions: PositionLike[] }

/** Есть ли в дереве хоть один исключённый (зачёркнутый) класс. */
export function hasExcludedChips(standards: StandardLike[]): boolean {
  return standards.some((s) =>
    s.positions.some((p) => p.chips.some((c) => c.state === "excluded"))
  )
}

/**
 * Легенда под деревом «Где разрешён». Пояснение про зачёркивание добавляем
 * ТОЛЬКО когда в выборке реально есть исключённый класс — иначе легенда
 * объясняла бы то, чего на экране нет.
 */
export function whereAllowedLegend(hasExcluded: boolean): string {
  const base = "показано текущее состояние стандартов"
  return hasExcluded
    ? `зачёркнутый класс — был в последнем релизе, исключён · ${base}`
    : base
}
