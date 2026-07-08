import { Button } from "@/components/ui/button"

function Swatch({ label, className }: { label: string; className: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div
        className={`h-12 w-full rounded-md border border-border ${className}`}
      />
      <span className="text-caption text-muted-foreground">{label}</span>
    </div>
  )
}

export function App() {
  return (
    <div className="min-h-svh bg-background p-8 text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="font-display text-h2">MR Design System</h1>
          <p className="text-body text-muted-foreground">
            Проверка токенов и тем. Нажмите <kbd>d</kbd> для переключения темы.
          </p>
        </header>

        <section className="flex flex-col gap-3">
          <h2 className="text-caption text-muted-foreground uppercase">
            Buttons
          </h2>
          <div className="flex flex-wrap gap-3">
            <Button>Primary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="subtle">Subtle</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Danger</Button>
            <Button variant="link">Link</Button>
            <Button disabled>Disabled</Button>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-caption text-muted-foreground uppercase">
            Surfaces & brand
          </h2>
          <div className="grid grid-cols-3 gap-4 sm:grid-cols-6">
            <Swatch label="background" className="bg-background" />
            <Swatch
              label="card + shadow"
              className="bg-card shadow-elevation-2"
            />
            <Swatch label="primary" className="bg-primary" />
            <Swatch label="violet-bright" className="bg-violet-bright" />
            <Swatch label="mint" className="bg-mint" />
            <Swatch label="tan" className="bg-tan" />
          </div>
        </section>
      </div>
    </div>
  )
}

export default App
