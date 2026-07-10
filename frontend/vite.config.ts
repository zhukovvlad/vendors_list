/// <reference types="vitest/config" />
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

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
    // префикс и шлёт на FastAPI (localhost:8000) — без CORS в разработке.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
})
