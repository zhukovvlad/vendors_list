import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach } from "vitest"

import { server } from "./msw/server"

// AppShell (rootRoute.component, Task 4) монтирует ThemeProvider-зависимый Toaster
// и shadcn Sidebar на КАЖДОМ роуте — оба используют API, которых нет в jsdom.
// Полифиллим глобально, а не в каждом тестовом файле по отдельности. Гард по
// typeof window: часть тестов (index.css.test.ts) идёт в @vitest-environment node,
// там window/Element не существуют вовсе.
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  }
  // Radix (DropdownMenu/Tooltip/Sidebar) в jsdom требует этих API — иначе меню/
  // тултип не открывается.
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
  // Radix DropdownMenuContent (позиционирование через Popper) использует
  // ResizeObserver — в jsdom его нет вовсе.
  if (!window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof window.ResizeObserver
  }
}

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
