import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router"
import { z } from "zod"

import { api } from "@/api/client"
import { DesignSystemShowcase } from "@/screens/DesignSystemShowcase"
import { MatrixScreen } from "@/screens/matrix/MatrixScreen"

const rootRoute = createRootRoute({ component: () => <Outlet /> })

const matrixSearchSchema = z.object({
  building_type_id: z.number().int().optional(),
  segment_id: z.number().int().optional(),
  q: z.string().optional(),
  offset: z.number().int().min(0).catch(0).default(0),
})

export const matrixRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: matrixSearchSchema,
  loaderDeps: ({ search }) => ({ building_type_id: search.building_type_id }),
  loader: async ({ deps }) => {
    // Дефолт типа объекта: невыразим в validateSearch (синхронный) — ставим тут,
    // после резолва /meta/building-types. Пустой список → без редиректа (пустое
    // состояние отрисует экран).
    if (deps.building_type_id === undefined) {
      const { data, error } = await api.GET("/meta/building-types")
      if (error) throw error
      const first = data?.[0]
      if (first) {
        throw redirect({
          to: "/",
          search: (prev) => ({ ...prev, building_type_id: first.id }),
        })
      }
    }
  },
  component: MatrixScreen,
})

const designSystemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/design-system",
  component: DesignSystemShowcase,
})

// Экспортируем routeTree: интеграционный тест (Task 9) строит memory-router из
// ЭТОГО ЖЕ дерева, поэтому matrixRoute.useSearch()/useNavigate() в экране резолвятся
// строго (те же route-инстансы), без нестрогих вариантов.
export const routeTree = rootRoute.addChildren([matrixRoute, designSystemRoute])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
