import { describe, expect, it } from "vitest"

import { sectionLabelForPath } from "./breadcrumb-map"

describe("sectionLabelForPath", () => {
  it("маппит известные разделы фазы 1", () => {
    expect(sectionLabelForPath("/")).toBe("Обзор")
    expect(sectionLabelForPath("/matrix")).toBe("Каталог стандартов")
    expect(sectionLabelForPath("/vendors")).toBe("Вендоры")
    expect(sectionLabelForPath("/design-system")).toBe("Дизайн-система")
  })

  it("неизвестный путь → пустая метка", () => {
    expect(sectionLabelForPath("/nope")).toBe("")
  })
})
