import { cva } from "class-variance-authority"

// Вынесено из badge.tsx, чтобы модуль компонента экспортировал только компонент
// (требование react-refresh / Fast Refresh).
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-caption font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        requirement: "border-warning/30 bg-warning/10 text-warning",
      },
    },
    defaultVariants: { variant: "default" },
  }
)
