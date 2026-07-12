import { describe, expect, it } from "vitest"

import {
  avatarInitial,
  excludedTooltip,
  hasExcludedChips,
  isAllClasses,
  kindLabel,
  pluralPositions,
  pluralStandards,
  pluralVendors,
  standardAllClasses,
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

describe("pluralPositions", () => {
  it("склоняет по числу", () => {
    expect(pluralPositions(1)).toBe("позиция")
    expect(pluralPositions(2)).toBe("позиции")
    expect(pluralPositions(4)).toBe("позиции")
    expect(pluralPositions(5)).toBe("позиций")
    expect(pluralPositions(0)).toBe("позиций")
    expect(pluralPositions(21)).toBe("позиция")
  })
  it("исключения 11–14 → «позиций»", () => {
    expect(pluralPositions(11)).toBe("позиций")
    expect(pluralPositions(12)).toBe("позиций")
    expect(pluralPositions(14)).toBe("позиций")
    expect(pluralPositions(111)).toBe("позиций")
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

describe("pluralStandards / pluralVendors", () => {
  it("склоняет стандарт", () => {
    expect(`${1} ${pluralStandards(1)}`).toBe("1 стандарт")
    expect(`${3} ${pluralStandards(3)}`).toBe("3 стандарта")
    expect(`${5} ${pluralStandards(5)}`).toBe("5 стандартов")
    expect(`${11} ${pluralStandards(11)}`).toBe("11 стандартов")
  })
  it("склоняет вендор", () => {
    expect(`${1} ${pluralVendors(1)}`).toBe("1 вендор")
    expect(`${2} ${pluralVendors(2)}`).toBe("2 вендора")
    expect(`${7} ${pluralVendors(7)}`).toBe("7 вендоров")
  })
})

describe("avatarInitial", () => {
  it("первая буква заглавная", () => {
    expect(avatarInitial("system air")).toBe("S")
    expect(avatarInitial("  ромашка")).toBe("Р")
  })
  it("пустое имя → ?", () => {
    expect(avatarInitial("   ")).toBe("?")
  })
})

describe("isAllClasses / standardAllClasses", () => {
  const pos = (states: string[]) => ({
    chips: states.map((state, i) => ({ segment_id: i, state })),
  })

  it("полное покрытие без excluded → все классы", () => {
    expect(isAllClasses(pos(["allowed", "allowed"]), 2)).toBe(true)
  })
  it("полное покрытие, но есть excluded → НЕ все классы (перечень)", () => {
    expect(isAllClasses(pos(["allowed", "allowed", "excluded"]), 3)).toBe(false)
  })
  it("частичное покрытие → НЕ все классы", () => {
    expect(isAllClasses(pos(["allowed", "allowed"]), 4)).toBe(false)
  })
  it("одноклассовый тип с покрытием → все классы", () => {
    expect(isAllClasses(pos(["allowed"]), 1)).toBe(true)
  })
  it("segment_count 0 → не все классы (страховка)", () => {
    expect(isAllClasses(pos([]), 0)).toBe(false)
  })

  it("стандарт: все позиции all-classes → true", () => {
    const std = {
      segment_count: 2,
      positions: [pos(["allowed", "allowed"]), pos(["allowed", "allowed"])],
    }
    expect(standardAllClasses(std)).toBe(true)
  })
  it("стандарт: хотя бы одна позиция не all-classes → false", () => {
    const std = {
      segment_count: 2,
      positions: [pos(["allowed", "allowed"]), pos(["allowed"])],
    }
    expect(standardAllClasses(std)).toBe(false)
  })
})
