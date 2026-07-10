import { describe, expect, it } from "vitest"

import { formatRelative, hasAttention } from "./model"
import type { Dashboard } from "./model"

const NOW = new Date("2026-07-10T12:00:00Z")

function iso(daysAgo: number): string {
  return new Date(NOW.getTime() - daysAgo * 86_400_000).toISOString()
}

describe("formatRelative", () => {
  it("сегодня / вчера / дни / недели с русским склонением", () => {
    expect(formatRelative(iso(0), NOW)).toBe("сегодня")
    expect(formatRelative(iso(1), NOW)).toBe("вчера")
    expect(formatRelative(iso(3), NOW)).toBe("3 дня назад")
    expect(formatRelative(iso(14), NOW)).toBe("2 недели назад")
  })
})

describe("hasAttention", () => {
  const base: Dashboard = {
    summary: {
      positions_active: 0,
      releases_published: 0,
      drafts_open: 0,
      vendors_total: 0,
      vendors_with_agreement: 0,
      merge_candidate_pairs: 0,
    },
    drafts: [],
  }

  it("false, когда кандидатов нет и нет залежавшихся", () => {
    expect(hasAttention(base)).toBe(false)
  })

  it("true, если есть кандидаты", () => {
    expect(hasAttention({ ...base, summary: { ...base.summary, merge_candidate_pairs: 6 } })).toBe(
      true
    )
  })

  it("null кандидатов трактуется как «нет пункта»", () => {
    expect(
      hasAttention({ ...base, summary: { ...base.summary, merge_candidate_pairs: null } })
    ).toBe(false)
  })

  it("true, если есть залежавшийся черновик", () => {
    const stale: Dashboard["drafts"][number] = {
      release_id: 1,
      building_type_name: "Жилые",
      label: "v1",
      last_touched_at: iso(30),
      last_touched_by: "a@b",
      is_stale: true,
    }
    expect(hasAttention({ ...base, drafts: [stale] })).toBe(true)
  })
})
