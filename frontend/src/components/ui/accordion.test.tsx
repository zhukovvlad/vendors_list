import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "./accordion"

describe("Accordion", () => {
  it("раскрывает контент по клику на триггер", async () => {
    render(
      <Accordion type="single" collapsible>
        <AccordionItem value="a">
          <AccordionTrigger>Заголовок</AccordionTrigger>
          <AccordionContent>Тело</AccordionContent>
        </AccordionItem>
      </Accordion>
    )
    await userEvent.click(screen.getByText("Заголовок"))
    expect(await screen.findByText("Тело")).toBeVisible()
  })
})
