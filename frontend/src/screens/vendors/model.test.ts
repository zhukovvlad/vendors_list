import { describe, expect, it } from "vitest"

import { excludedTooltip, kindLabel } from "./model"

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
