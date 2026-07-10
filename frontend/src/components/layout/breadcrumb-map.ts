/**
 * Метка раздела для хлебной крошки по pathname активного роута.
 *
 * Чистая функция — задел под глубокие уровни каталога (тип объекта, издание):
 * дополнительные крошки допишутся здесь без правок в шапке.
 */
const SECTION_LABELS: Record<string, string> = {
  "/": "Обзор",
  "/matrix": "Каталог стандартов",
  "/vendors": "Вендоры",
  "/design-system": "Дизайн-система",
}

export function sectionLabelForPath(pathname: string): string {
  return SECTION_LABELS[pathname] ?? ""
}
