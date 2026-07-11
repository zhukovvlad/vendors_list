import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"

import { useVendor } from "@/api/queries"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { vendorCardRoute } from "@/router"

import { kindLabel } from "./model"

export function VendorCardScreen() {
  const { vendorId } = vendorCardRoute.useParams()
  const id = Number(vendorId)
  const { data, isPending, isError } = useVendor(id)

  if (isPending)
    return <div className="py-16 text-center text-muted-foreground">Загрузка…</div>
  if (isError || !data)
    return <div className="py-16 text-center text-muted-foreground">Вендор не найден</div>

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-h3 font-medium">{data.name}</h1>
          <Badge variant="outline">{kindLabel(data.kind)}</Badge>
          {data.starred && (
            <Badge variant="outline" className="gap-1">
              <Star className="size-3 fill-current" aria-hidden />
              соглашение
            </Badge>
          )}
          <span className="flex-1" />
          <label className="flex items-center gap-2 text-small">
            Соглашение
            <Switch
              checked={data.starred}
              disabled
              aria-label="Соглашение о сотрудничестве"
            />
          </label>
        </div>
        <div className="text-small text-muted-foreground">
          {data.represents ? (
            <>
              представляет:{" "}
              <Link
                to="/vendors/$vendorId"
                params={{ vendorId: String(data.represents.id) }}
                className="underline"
              >
                {data.represents.name}
              </Link>
            </>
          ) : (
            "самостоятельный бренд"
          )}
        </div>
      </header>

      {data.note && (
        <p data-testid="vendor-note" className="text-small">
          {data.note}
        </p>
      )}

      <section className="space-y-2">
        <div className="text-caption uppercase text-muted-foreground">
          Варианты написания
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.aliases.length === 0 && (
            <span className="text-small text-muted-foreground">—</span>
          )}
          {data.aliases.map((a) => (
            <Badge key={a.id} variant="outline">
              {a.alias}
            </Badge>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-caption uppercase text-muted-foreground">
          Бренд и объединение
        </div>
        {data.represented_count > 0 && (
          <div className="text-small text-muted-foreground">
            {data.represented_count} брендов представлены этим
          </div>
        )}
        <Button variant="outline" disabled title="в разработке">
          Объединить
        </Button>
      </section>
    </div>
  )
}
