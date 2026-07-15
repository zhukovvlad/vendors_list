import { describe, expect, it } from "vitest"

import { splitQualifier } from "./qualifier"

describe("splitQualifier", () => {
  it("без скобки → qualifier null", () => {
    expect(splitQualifier("Радиаторы")).toEqual({
      head: "Радиаторы",
      qualifier: null,
    })
  })
  it("со скобкой → голова и уточнение", () => {
    expect(splitQualifier("Насосы (EC двигатель)")).toEqual({
      head: "Насосы",
      qualifier: "EC двигатель",
    })
  })
  it("несбалансированная скобка → всё после '(' как уточнение", () => {
    expect(splitQualifier("Клапаны (Ду50")).toEqual({
      head: "Клапаны",
      qualifier: "Ду50",
    })
  })
})
