/**
 * Блок пользователя в футере сайдбара.
 *
 * Имя/роль/инициалы — временный плейсхолдер до боевого SSO/RBAC (ТЗ §2);
 * пункты Профиль/Настройки/Выход неактивны.
 */
import { MoreVertical } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

// TODO(§2): заменить на данные из боевого SSO/RBAC.
const USER = { name: "Владимир Ж.", role: "Редактор", initials: "ВЖ" } as const

export function UserMenu() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" tooltip={USER.name}>
              <Avatar className="h-7 w-7">
                <AvatarFallback>{USER.initials}</AvatarFallback>
              </Avatar>
              <div className="flex flex-col text-left leading-tight group-data-[collapsible=icon]:hidden">
                <span className="text-sm">{USER.name}</span>
                <span className="text-xs text-muted-foreground">
                  {USER.role}
                </span>
              </div>
              <MoreVertical className="ml-auto h-4 w-4 group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end">
            <DropdownMenuLabel>{USER.name}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>Профиль</DropdownMenuItem>
            <DropdownMenuItem disabled>Настройки</DropdownMenuItem>
            <DropdownMenuItem disabled>Выход</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
