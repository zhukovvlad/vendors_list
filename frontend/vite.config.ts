/// <reference types="vitest/config" />
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Порт бэкенда конфигурируем через env: на общей машине :8000 часто занят чужим
// процессом, а uvicorn на Windows из-за SO_REUSEADDR молча «стартует» на занятом
// порту (трафик уходит первому владельцу). Каждый разработчик задаёт свой свободный
// порт через VENDORS_BACKEND_PORT (должен совпадать с `just dev-back`). 127.0.0.1
// вместо localhost — чтобы прокси не ушёл в IPv6 (::1), где бэкенда может не быть.
const backendPort = process.env.VENDORS_BACKEND_PORT ?? "8000"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // api/client.ts иначе берёт относительный baseUrl "/api": openapi-fetch строит
    // запрос через `new Request(url, init)`, а в jsdom/Node (в отличие от браузера)
    // глобальный Request не резолвит относительный URL против "текущего документа" —
    // падает `TypeError: Failed to parse URL from /api/...`. Абсолютный URL на
    // дефолтном origin jsdom (http://localhost:3000) чинит и Request(), и матчинг
    // MSW-обработчиков (объявлены относительным путём "/api/...", MSW сверяет
    // по итоговому abs-URL на том же origin).
    env: { VITE_API_URL: "http://localhost:3000/api" },
  },
  server: {
    // Прокси на бэкенд: фронт зовёт относительный /api/*, дев-сервер снимает
    // префикс и шлёт на FastAPI (127.0.0.1:${VENDORS_BACKEND_PORT}) — без CORS в разработке.
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
})
