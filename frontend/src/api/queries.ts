/**
 * Хуки данных на TanStack Query поверх типизированного клиента.
 * Примеры покрывают главный сценарий (просмотр): матрица перечня и сводка проекта.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query"

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
