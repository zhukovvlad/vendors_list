/**
 * Корневая оболочка приложения: сайдбар + тонкая шапка + область контента.
 *
 * ThemeProvider здесь НЕ оборачиваем — он уже в main.tsx над RouterProvider.
 * Встраивается как rootRoute.component, поэтому все роуты получают оболочку.
 */
import { Outlet } from "@tanstack/react-router"

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"

import { AppHeader } from "./AppHeader"
import { AppSidebar } from "./AppSidebar"

export function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <AppHeader />
        <div className="px-4 py-4">
          <Outlet />
        </div>
      </SidebarInset>
      <Toaster richColors position="bottom-right" />
    </SidebarProvider>
  )
}
