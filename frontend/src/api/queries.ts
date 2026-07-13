/**
 * Хуки данных на TanStack Query поверх типизированного клиента.
 * Примеры покрывают главный сценарий (просмотр): матрица перечня и сводка проекта.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import { api } from "./client"

export function useListings(params?: {
  segment_id?: number
  position_id?: number
  q?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["listings", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/listings", {
        params: { query: params },
      })
      if (error) throw error
      return data
    },
  })
}

export function useProjectSummary(projectId: number) {
  return useQuery({
    queryKey: ["project-summary", projectId],
    queryFn: async () => {
      const { data, error } = await api.GET("/projects/{project_id}/summary", {
        params: { path: { project_id: projectId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useProjectPositions(projectId: number) {
  return useQuery({
    queryKey: ["project-positions", projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/projects/{project_id}/positions",
        {
          params: { path: { project_id: projectId } },
        }
      )
      if (error) throw error
      return data
    },
  })
}

// Сужаем data: openapi-fetch отдаёт data как T | undefined. После throw на error
// data всё ещё возможно-undefined по типу — гвардим, чтобы хук вернул T, а не
// T | undefined (иначе typecheck встанет на обращениях без ?.). См. Task 0 Step 3.
export function useMatrix(params: {
  building_type_id: number
  segment_id?: number
  q?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["matrix", params],
    // При смене фильтров (новый queryKey) держим предыдущие данные вместо
    // undefined: не мигаем пустой таблицей на латентности сети и не отдаём
    // useReactTable нестабильный `?? []` (новый [] на каждый рендер — ловушка
    // бесконечного ре-рендера из FAQ TanStack Table).
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.GET("/listings/matrix", {
        params: { query: params },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /listings/matrix")
      return data
    },
  })
}

export function useBuildingTypes() {
  return useQuery({
    queryKey: ["building-types"],
    queryFn: async () => {
      const { data, error } = await api.GET("/meta/building-types")
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/building-types")
      return data
    },
  })
}

export function useSegments(buildingTypeId?: number) {
  return useQuery({
    queryKey: ["segments", buildingTypeId],
    enabled: buildingTypeId !== undefined,
    queryFn: async () => {
      const { data, error } = await api.GET("/meta/segments", {
        params: { query: { building_type_id: buildingTypeId } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/segments")
      return data
    },
  })
}

/**
 * Позиции типа объекта для комбобокса «+ стандарт» (поиск по q). `building_type_id`
 * обязателен в контракте API — гвардим на undefined внутри queryFn (typecheck),
 * хотя `enabled` и не даёт queryFn реально выполниться раньше выбора стандарта.
 */
export function useMetaPositions(buildingTypeId?: number, q?: string) {
  return useQuery({
    queryKey: ["meta-positions", buildingTypeId, q],
    enabled: buildingTypeId !== undefined,
    queryFn: async () => {
      if (buildingTypeId === undefined)
        throw new Error("useMetaPositions: building_type_id не задан")
      const { data, error } = await api.GET("/meta/positions", {
        params: { query: { building_type_id: buildingTypeId, q } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /meta/positions")
      return data
    },
  })
}

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => {
      const { data, error } = await api.GET("/dashboard")
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /dashboard")
      return data
    },
  })
}

/** Карточка вендора по id (шапка). Бросает на ошибке API или пустом ответе. */
export function useVendor(id: number) {
  return useQuery({
    queryKey: ["vendor", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/vendors/{vendor_id}", {
        params: { path: { vendor_id: id } },
      })
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /vendors/{id}")
      return data
    },
  })
}

/** Дерево «Где разрешён» по id. Бросает на ошибке API или пустом ответе. */
export function useVendorWhereAllowed(id: number) {
  return useQuery({
    queryKey: ["vendor-where-allowed", id],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/vendors/{vendor_id}/where-allowed",
        {
          params: { path: { vendor_id: id } },
        }
      )
      if (error) throw error
      if (!data) throw new Error("Пустой ответ /vendors/{id}/where-allowed")
      return data
    },
  })
}

/**
 * Мутация тумблера соглашения (O1). На успехе инвалидирует карточку вендора,
 * а также матрицу и дашборд — звезда вендора в матрице и счётчик соглашений на
 * дашборде зависят от флага, иначе показывали бы устаревшее состояние.
 */
export function useToggleAgreement(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (active: boolean) => {
      const { data, error } = await api.PUT("/vendors/{vendor_id}/agreement", {
        params: { path: { vendor_id: id } },
        body: { active },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor", id] })
      qc.invalidateQueries({ queryKey: ["matrix"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}

/** Мутация добавления alias вендора; на успехе инвалидирует карточку. */
export function useAddAlias(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (alias: string) => {
      const { data, error } = await api.POST("/vendors/{vendor_id}/aliases", {
        params: { path: { vendor_id: id } },
        body: { alias },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", id] }),
  })
}

/** Мутация удаления alias вендора по id alias'а; на успехе инвалидирует карточку. */
export function useRemoveAlias(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (aliasId: number) => {
      const { error } = await api.DELETE(
        "/vendors/{vendor_id}/aliases/{alias_id}",
        {
          params: { path: { vendor_id: id, alias_id: aliasId } },
        }
      )
      if (error) throw error
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", id] }),
  })
}

/**
 * Мутация инлайн-правки шапки (имя/примечание, partial). На успехе инвалидирует
 * карточку, а также матрицу и дашборд (имя вендора видно в обоих).
 */
export function useUpdateVendorHeader(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (fields: {
      name?: string
      note?: string
      kind?: string
    }) => {
      const { data, error } = await api.PATCH("/vendors/{vendor_id}", {
        params: { path: { vendor_id: id } },
        body: fields,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor", id] })
      qc.invalidateQueries({ queryKey: ["matrix"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}

/** Инвалидация после мутации разрешений: 4 ключа (дерево + карточка + матрица + дашборд). */
function invalidatePermissions(
  qc: ReturnType<typeof useQueryClient>,
  id: number
) {
  qc.invalidateQueries({ queryKey: ["vendor-where-allowed", id] })
  qc.invalidateQueries({ queryKey: ["vendor", id] })
  qc.invalidateQueries({ queryKey: ["matrix"] })
  qc.invalidateQueries({ queryKey: ["dashboard"] })
}

/** Добавить вендора в позицию по классам (общий «+ класс»/«+ позиция»/«+ стандарт»). */
export function useAddListings(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      position_id: number
      segment_ids: number[]
    }) => {
      const { error } = await api.POST("/vendors/{vendor_id}/listings", {
        params: { path: { vendor_id: id } },
        body,
      })
      if (error) throw error
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}

/** Исключить вендора по scope; возвращает фактический масштаб (для тоста). */
export function useExcludeListings(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      scope: "class" | "position" | "standard"
      position_id?: number
      segment_id?: number
      building_type_id?: number
    }) => {
      const { data, error } = await api.POST(
        "/vendors/{vendor_id}/listings/exclude",
        {
          params: { path: { vendor_id: id } },
          body,
        }
      )
      if (error) throw error
      return data
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}

/** «Вернуть» один класс. */
export function useRestoreListing(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { position_id: number; segment_id: number }) => {
      const { error } = await api.POST(
        "/vendors/{vendor_id}/listings/restore",
        {
          params: { path: { vendor_id: id } },
          body,
        }
      )
      if (error) throw error
    },
    onSuccess: () => invalidatePermissions(qc, id),
  })
}
