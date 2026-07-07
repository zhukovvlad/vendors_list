/**
 * Типизированный API-клиент. Типы берутся из schema.d.ts, сгенерированной из
 * OpenAPI бэкенда (`just types`) — сквозная типизация без общего рантайма.
 *
 * В dev запросы идут на `/api` и проксируются Vite на бэкенд (см. vite.config.ts),
 * поэтому CORS в разработке не мешает. Базовый URL можно переопределить через
 * VITE_API_URL (например, абсолютный адрес прод-API).
 */
import createClient from "openapi-fetch"

import type { paths } from "./schema"

const baseUrl = import.meta.env.VITE_API_URL ?? "/api"

export const api = createClient<paths>({ baseUrl })

// TODO(auth): в проде подставлять bearer-токен из OIDC-сессии:
// api.use({ onRequest({ request }) { request.headers.set("Authorization", `Bearer ${token}`); return request } })
