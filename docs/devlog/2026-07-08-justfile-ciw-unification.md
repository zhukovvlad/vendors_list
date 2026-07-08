# 2026-07-08 — Унификация команд с CIW + UTF-8 в консоли

Привёл `justfile` в соответствие с соседним проектом CIW, чтобы команды и
поведение совпадали между проектами.

- **Оболочка** переведена с bash на **PowerShell** (`set windows-shell`), как
  в CIW: команды в строке через `;`, каждая строка рецепта — отдельный вызов
  (cwd сбрасывается на корень, поэтому строки в подкаталоге начинаются с
  `cd {{backend}};`).
- **Единый словарь команд:** `install`, `migrate`, `migrate-down`,
  `makemigration`, `dev-back`, `dev-front`, `lint`, `fmt`, `test`, `build`.
  Осознанное расхождение: `makemigration` БЕЗ `--autogenerate` (у нас
  schema-first, autogenerate запрещён) — создаёт пустую ревизию под ручной SQL.
  Наши доп. команды поверх CIW: `types` (OpenAPI→TS), `typecheck`, `ci`.
- **Кракозябры устранены.** PowerShell 5.1 писал в консоль в OEM cp866 →
  кириллица билась. В `-Command`-префиксе форсирован UTF-8:
  `[Console]::OutputEncoding = UTF8` (для PowerShell) и `$env:PYTHONUTF8=1`
  (для дочерних python/alembic/uv).
- Во фронт добавлен скрипт `format:check` (prettier --check), а `schema.d.ts`
  (генерируемый) внесён в `.prettierignore`, чтобы `lint` был стабилен.
- Доки (README, CLAUDE.md, DEVELOPMENT) обновлены под новые имена команд.

Проверено: `just ci` (types → lint → typecheck → test) зелёный, вывод — без
кракозябр.
