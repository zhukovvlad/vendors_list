# Task runner для «Учёт вендор-листов» (Vendors).
# Бэкенд работает строго в .venv через `uv run`. Docker не используется.
# Команды унифицированы с соседним проектом CIW (одинаковый словарь).
#
# Используется Windows PowerShell 5.1, который НЕ поддерживает оператор `&&`,
# поэтому команды внутри одной строки разделяются `;` (каждая строка рецепта
# выполняется в отдельном вызове оболочки, cwd сбрасывается на корень проекта —
# поэтому строки, работающие в подкаталоге, начинаются с `cd {{backend}};`).
#
# Префикс -Command форсирует UTF-8 на вывод (иначе кириллица в консоли —
# кракозябры из-за OEM-кодировки cp866): [Console]::OutputEncoding для самого
# PowerShell + PYTHONUTF8 для дочерних python/alembic/uv.
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", "$env:PYTHONUTF8='1'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"]

backend := "backend"
frontend := "frontend"

# Список доступных команд.
default:
    @just --list

# Установка зависимостей бэкенда (.venv через uv) и фронтенда.
install:
    cd {{backend}}; uv sync
    cd {{frontend}}; npm install

# Применить миграции к БД (alembic upgrade head). Требует DATABASE_URL в backend/.env.
# MIGRATE_TARGET явно зануляется: если в сессии остался экспортированный
# MIGRATE_TARGET=test, этот рецепт всё равно должен идти в основную БД.
migrate:
    cd {{backend}}; $env:MIGRATE_TARGET=''; uv run alembic upgrade head

# Накатить миграции на ТЕСТОВУЮ ветку (DATABASE_URL_TEST). На data+schema-ветке,
# унаследовавшей alembic_version от production, это no-op (применит только
# реально новые ревизии). Прод не трогает.
migrate-test:
    cd {{backend}}; $env:MIGRATE_TARGET='test'; uv run alembic upgrade head

# Откатить последнюю миграцию.
migrate-down:
    cd {{backend}}; $env:MIGRATE_TARGET=''; uv run alembic downgrade -1

# История/статус миграций.
migrate-history:
    cd {{backend}}; uv run alembic history --verbose
migrate-current:
    cd {{backend}}; $env:MIGRATE_TARGET=''; uv run alembic current

# ВНИМАНИЕ: в отличие от CIW здесь НЕТ --autogenerate — схемой владеет БД
# (schema-first), правку пишем вручную через op.execute в созданной ревизии.
#
# Новая ПУСТАЯ ревизия под ручной SQL: just makemigration name="add index".
makemigration name:
    cd {{backend}}; uv run alembic revision -m "{{name}}"

# Запуск FastAPI (hot-reload) в виртуальном окружении. API на :8000, /docs.
dev-back:
    cd {{backend}}; uv run uvicorn app.main:app --reload --port 8000

# Запуск Vite dev-сервера (:5173, проксирует /api -> :8000).
dev-front:
    cd {{frontend}}; npm run dev

# Сквозная типизация: OpenAPI бэкенда -> TS-типы фронта (frontend/src/api/schema.d.ts).
types:
    cd {{backend}}; uv run python -m scripts.export_openapi
    npx --yes openapi-typescript {{backend}}/openapi.json -o {{frontend}}/src/api/schema.d.ts

# Линтинг бэкенда (ruff) и фронтенда (eslint + prettier --check).
lint:
    cd {{backend}}; uv run ruff check .
    cd {{frontend}}; npm run lint
    cd {{frontend}}; npm run format:check

# Автоформатирование/исправление.
fmt:
    cd {{backend}}; uv run ruff check --fix .; uv run ruff format .
    cd {{frontend}}; npm run format

# Проверка типов: бэкенд (mypy) и фронтенд (tsc).
typecheck:
    cd {{backend}}; uv run mypy app
    cd {{frontend}}; npm run typecheck

# Тесты бэкенда (pytest). Тесты фронта (vitest) — TODO, пока не заведены.
test:
    cd {{backend}}; uv run pytest

# Production-сборка фронтенда.
build:
    cd {{frontend}}; npm run build

# Полный прогон проверок как в CI (типы генерируем до линта/тайпчека/сборки).
ci: types lint typecheck test
    @echo "OK: все проверки прошли"
