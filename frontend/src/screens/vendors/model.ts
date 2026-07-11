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

export const WHERE_ALLOWED_LEGEND =
  "зачёркнутый класс — был в последнем релизе, исключён · показано текущее состояние стандартов"
