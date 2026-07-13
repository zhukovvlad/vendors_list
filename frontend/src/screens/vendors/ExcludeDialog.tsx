import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

import { pluralClasses, pluralPositions } from "./model"

interface ExcludeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  scale: { positions: number; classes: number }
  pending: boolean
  onConfirm: () => void
}

/**
 * Подтверждение массового исключения (позиция/стандарт). Масштаб — клиентский
 * предрасчёт из уже загруженного дерева (мгновенно, без сети); фактический масштаб
 * придёт в тосте из ответа мутации. Точечное исключение (класс) диалога НЕ требует.
 */
export function ExcludeDialog({
  open,
  onOpenChange,
  title,
  scale,
  pending,
  onConfirm,
}: ExcludeDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Будет исключён из {scale.positions}{" "}
            {pluralPositions(scale.positions)} и {scale.classes}{" "}
            {pluralClasses(scale.classes)}. Исключение применится сразу и войдёт
            в следующий релиз; текущие релизы не затрагиваются.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            Исключить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
