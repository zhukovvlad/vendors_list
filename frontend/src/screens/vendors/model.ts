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

/** Русское склонение слова «позиция» по числу (1 позиция / 2 позиции / 5 позиций). */
export function pluralPositions(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return "позиция"
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "позиции"
  return "позиций"
}

/** Русское склонение «стандарт» по числу. */
export function pluralStandards(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return "стандарт"
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "стандарта"
  return "стандартов"
}

/** Русское склонение «вендор» по числу. */
export function pluralVendors(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return "вендор"
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "вендора"
  return "вендоров"
}

/** Инициал для аватар-плитки: первая непробельная буква имени, заглавная. */
export function avatarInitial(name: string): string {
  const ch = name.trim().charAt(0)
  return ch ? ch.toUpperCase() : "?"
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

/** Стандарт для правила «все классы»: `PositionLike` + знаменатель `segment_count`. */
type CoverageStandard = { segment_count: number; positions: PositionLike[] }

/** Есть ли в дереве хоть один исключённый (зачёркнутый) класс. */
export function hasExcludedChips(standards: StandardLike[]): boolean {
  return standards.some((s) =>
    s.positions.some((p) => p.chips.some((c) => c.state === "excluded"))
  )
}

/**
 * Позиция покрыта «все классы»: вендор разрешён во ВСЕХ сегментах типа и нет
 * исключённых. `excluded > 0` всегда даёт false — исключение не прячется за сводкой.
 */
export function isAllClasses(
  position: PositionLike,
  segmentCount: number
): boolean {
  if (segmentCount <= 0) return false
  let allowed = 0
  let excluded = 0
  for (const c of position.chips) {
    if (c.state === "allowed") allowed++
    else if (c.state === "excluded") excluded++
  }
  return excluded === 0 && allowed === segmentCount
}

/** Стандарт целиком «все классы»: он непустой и все его позиции — «все классы». */
export function standardAllClasses(standard: CoverageStandard): boolean {
  return (
    standard.positions.length > 0 &&
    standard.positions.every((p) => isAllClasses(p, standard.segment_count))
  )
}

/**
 * Базовая легенда под деревом «Где разрешён» («показано текущее состояние
 * стандартов»). Вариант с пояснением про зачёркивание рендерится инлайн в
 * компоненте (с визуальным образцом-чипом), когда в выборке есть исключённый
 * класс, — поэтому здесь только базовый текст.
 */
export function whereAllowedLegend(): string {
  return "показано текущее состояние стандартов"
}
