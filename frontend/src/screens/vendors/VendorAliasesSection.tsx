import { useState } from "react"
import { Plus, X } from "lucide-react"

import { useAddAlias, useRemoveAlias } from "@/api/queries"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

import { CARD } from "./model"

type Alias = { id: number; alias: string }

/**
 * Секция «Варианты написания»: чипы алиасов + правка в edit (× на чипе, «+ вариант»
 * с инлайн-инпутом). Владеет мутациями и локальным состоянием ввода (`aliasOpen`/
 * `aliasDraft`) — набор варианта не перерисовывает остальную карточку.
 * Мутации — `useMutation`, сети на маунте нет: тайминг монтирования не важен.
 */
export function VendorAliasesSection({
  id,
  aliases,
  editMode,
}: {
  id: number
  aliases: Alias[]
  editMode: boolean
}) {
  const addAlias = useAddAlias(id)
  const removeAlias = useRemoveAlias(id)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")

  return (
    <section className={`${CARD} px-5 py-[15px]`}>
      <div className="mb-2.5 text-caption text-muted-foreground uppercase">
        Варианты написания
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {aliases.length === 0 && (
          <span className="text-small text-muted-foreground">
            вариантов пока нет
          </span>
        )}
        {aliases.map((a) => (
          <Badge key={a.id} variant="outline" className="gap-1">
            {a.alias}
            {editMode && (
              <button
                type="button"
                aria-label={`удалить ${a.alias}`}
                onClick={() => removeAlias.mutate(a.id)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            )}
          </Badge>
        ))}
        {editMode &&
          (aliasOpen ? (
            <span className="flex items-center gap-1">
              <input
                autoFocus
                value={aliasDraft}
                onChange={(e) => setAliasDraft(e.target.value)}
                placeholder="вариант написания"
                className="h-7 rounded-md border border-border bg-transparent px-2 text-small"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={aliasDraft.trim() === "" || addAlias.isPending}
                onClick={() => {
                  addAlias.mutate(aliasDraft.trim(), {
                    onSuccess: () => {
                      setAliasDraft("")
                      setAliasOpen(false)
                    },
                  })
                }}
              >
                Добавить
              </Button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setAliasOpen(true)}
              className="inline-flex items-center gap-1 rounded-md border border-dashed border-border-strong px-2.5 py-1 text-small text-primary"
            >
              <Plus className="size-3" aria-hidden />
              вариант
            </button>
          ))}
      </div>
    </section>
  )
}
