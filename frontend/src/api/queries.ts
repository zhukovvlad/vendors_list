/**
 * Хуки данных на TanStack Query поверх типизированного клиента.
 * Примеры покрывают главный сценарий (просмотр): матрица перечня и сводка проекта.
 */
import { useQuery } from "@tanstack/react-query"

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
