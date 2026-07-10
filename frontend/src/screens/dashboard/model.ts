import type { components } from "@/api/schema"

export type Dashboard = components["schemas"]["Dashboard"]
export type DashboardDraft = components["schemas"]["DashboardDraft"]
export type DashboardSummary = components["schemas"]["DashboardSummary"]

function plural(n: number, forms: [string, string, string]): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return forms[0]
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1]
  return forms[2]
}

/** Относительное время правки: «сегодня» / «вчера» / «N дней|недель назад». */
export function formatRelative(iso: string, now: Date): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return "сегодня"
  if (days === 1) return "вчера"
  if (days < 7) return `${days} ${plural(days, ["день", "дня", "дней"])} назад`
  const weeks = Math.floor(days / 7)
  return `${weeks} ${plural(weeks, ["неделю", "недели", "недель"])} назад`
}

/** Есть ли что показать в «Требует внимания» (кандидаты или залежавшиеся). */
export function hasAttention(d: Dashboard): boolean {
  const pairs = d.summary.merge_candidate_pairs
  return (pairs != null && pairs > 0) || d.drafts.some((x) => x.is_stale)
}
