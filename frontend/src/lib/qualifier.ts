/**
 * Делит имя позиции на «голову» и уточнение в скобках для презентации (первая
 * открывающая скобка). «Насосы (EC двигатель)» → {head:"Насосы", qualifier:"EC двигатель"}.
 * Нет скобки → qualifier=null. Презентационно, НЕ парсер данных.
 */
export function splitQualifier(name: string): {
  head: string
  qualifier: string | null
} {
  const i = name.indexOf("(")
  if (i === -1) return { head: name.trim(), qualifier: null }
  const head = name.slice(0, i).trim()
  const rest = name.slice(i + 1)
  const close = rest.lastIndexOf(")")
  const qualifier = (close === -1 ? rest : rest.slice(0, close)).trim()
  return { head: head || name.trim(), qualifier: qualifier || null }
}
