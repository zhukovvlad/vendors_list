import { describe, expect, it } from "vitest"

import {
  excludedTooltip,
  hasExcludedChips,
  kindLabel,
  whereAllowedLegend,
} from "./model"

describe("kindLabel", () => {
  it("локализует известные типы", () => {
    expect(kindLabel("manufacturer")).toBe("производитель")
    expect(kindLabel("supplier")).toBe("поставщик")
    expect(kindLabel("other")).toBe("прочее")
  })
  it("неизвестное значение отдаёт как есть", () => {
    expect(kindLabel("weird")).toBe("weird")
  })
})

describe("excludedTooltip", () => {
  it("вставляет label релиза", () => {
    expect(excludedTooltip("ред. 25.03")).toContain("«ред. 25.03»")
  })
  it("без label — обобщённо", () => {
    expect(excludedTooltip(null)).toBe(
      "Был в последнем релизе, исключён в текущем черновике"
    )
  })
})

describe("hasExcludedChips", () => {
  it("true, когда есть хотя бы один excluded-чип", () => {
    expect(
      hasExcludedChips([
        {
          positions: [{ chips: [{ state: "allowed" }, { state: "excluded" }] }],
        },
      ])
    ).toBe(true)
  })
  it("false, когда все чипы allowed", () => {
    expect(
      hasExcludedChips([{ positions: [{ chips: [{ state: "allowed" }] }] }])
    ).toBe(false)
  })
  it("false на пустом дереве", () => {
    expect(hasExcludedChips([])).toBe(false)
  })
})

describe("whereAllowedLegend", () => {
  it("с исключёнными — добавляет пояснение про зачёркивание", () => {
    const legend = whereAllowedLegend(true)
    expect(legend).toContain("зачёркнутый класс")
    expect(legend).toContain("показано текущее состояние стандартов")
  })
  it("без исключённых — только общая часть, без пояснения про зачёркивание", () => {
    expect(whereAllowedLegend(false)).toBe(
      "показано текущее состояние стандартов"
    )
  })
})
