/** Тонкая шапка контента: триггер сворачивания сайдбара + хлебная крошка. */
import { useRouterState } from "@tanstack/react-router"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb"
import { SidebarTrigger } from "@/components/ui/sidebar"

import { sectionLabelForPath } from "./breadcrumb-map"

export function AppHeader() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const label = sectionLabelForPath(pathname)

  return (
    <header className="flex h-14 items-center gap-3 border-b px-4">
      <SidebarTrigger />
      {label && (
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>{label}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      )}
    </header>
  )
}
