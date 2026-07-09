import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach } from "vitest"

import { server } from "./msw/server"

// listen() зовём синхронно на верхнем уровне setupFiles (а не внутри beforeAll):
// setupFiles импортируются и целиком выполняются раньше самого тестового модуля,
// поэтому к моменту, когда тестовый файл потянет `@/api/client`, глобальные
// fetch/Request уже патчены MSW. openapi-fetch кеширует `globalThis.fetch`/
// `globalThis.Request` ОДИН раз при вызове createClient() (на импорте модуля) —
// если бы listen() был внутри beforeAll (выполняется уже после импорта тестового
// файла и всех его зависимостей), клиент навсегда закешировал бы непропатченный
// fetch и реальные сетевые запросы уходили бы мимо MSW.
server.listen({ onUnhandledRequest: "error" })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
