import { describe, expect, it } from "vitest"

import { api } from "@/api/client"

describe("api client", () => {
  it("экспортирует настроенный openapi-fetch клиент", () => {
    expect(api).toBeDefined()
    expect(typeof api.GET).toBe("function")
  })
})
