/**
 * Боковая навигация приложения (фаза 1).
 *
 * Содержит рабочие разделы + системный футер (Админка-заглушка и dev-витрина).
 * Контрол темы и блок пользователя добавляются в футер отдельно (ThemeControl,
 * UserMenu). Ссылки — TanStack <Link>; активность считаем из pathname.
 */
import { Link, useRouterState } from "@tanstack/react-router"
import {
  Building2,
  LayoutDashboard,
  Palette,
  Settings,
  Table2,
} from "lucide-react"

import { isDevBuild } from "@/lib/env"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"

import { ThemeControl } from "./ThemeControl"
import { UserMenu } from "./UserMenu"

const NAV = [
  { title: "Обзор", to: "/", icon: LayoutDashboard, exact: true },
  { title: "Каталог стандартов", to: "/matrix", icon: Table2, exact: false },
  { title: "Вендоры", to: "/vendors", icon: Building2, exact: false },
] as const

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isActive = (to: string, exact?: boolean) =>
    exact ? pathname === to : pathname === to || pathname.startsWith(`${to}/`)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link to="/" className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-medium text-sidebar-primary-foreground">
            М
          </div>
          <span className="text-sm font-medium group-data-[collapsible=icon]:hidden">
            Вендор-листы
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.to, item.exact)}
                    tooltip={item.title}
                  >
                    <Link to={item.to}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarSeparator />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton disabled tooltip="Админка — в разработке">
              <Settings />
              <span>Админка</span>
              <span className="ml-auto text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                в разработке
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {isDevBuild() && (
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                isActive={isActive("/design-system")}
                tooltip="Дизайн-система"
              >
                <Link to="/design-system">
                  <Palette />
                  <span>Дизайн-система</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
        <ThemeControl />
        <UserMenu />
      </SidebarFooter>
    </Sidebar>
  )
}
