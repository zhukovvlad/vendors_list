import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Card, CardContent, CardHeader, CardTitle } from "./card"

describe("Card", () => {
  it("рендерит заголовок и содержимое", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Фильтры</CardTitle>
        </CardHeader>
        <CardContent>тело</CardContent>
      </Card>
    )
    expect(screen.getByText("Фильтры")).toBeInTheDocument()
    expect(screen.getByText("тело")).toBeInTheDocument()
  })
})
