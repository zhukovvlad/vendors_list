# 2026-07-09 — Матрица перечня (первый продуктовый экран)

Ветка `feat/listing-matrix`. Реализовано по методике subagent-driven-development
(план [docs/superpowers/plans/2026-07-09-listing-matrix.md](../superpowers/plans/2026-07-09-listing-matrix.md),
спека [.../specs/2026-07-09-listing-matrix-design.md](../superpowers/specs/2026-07-09-listing-matrix-design.md)):
10 задач (5 срезов + финал), свежий субагент-исполнитель на каждую + ревью,
Task 0 Preflight перед стартом (сверка сигнатуры `category_path`, `baseUrl`,
`undefined`-политики openapi-fetch с фактическим кодом репо).

Цель — первый продуктовый экран поверх read-only API (ТЗ §4.1): вендор-лист
как матрица «раздел × building_type/segment» с ячейками-требованиями и
серверной пагинацией по позициям.

## Что сделано

- **`category_sort_path`** ([backend/migrations/](../../backend/migrations/)) —
  SQL-функция, возвращает `int[]` — preorder-путь по дереву категорий, отсортированный
  по кураторскому `sort_order` (не по алфавиту), с детерминизмом при дублях
  `sort_order` через пару `[sort_order, id]`. db-тесты (инвертированный TDD —
  ждём PASS с первого прогона): `test_preorder_by_sort_order_not_alphabet`,
  `test_deterministic_on_duplicate_sort_order`, `test_parent_prefixes_child`.
- **`GET /listings/matrix`** (server pivot, без новой вьюхи) — шейпинг в
  Python-роутере поверх `listing_live`: CTE `pos_page` пагинирует по
  `DISTINCT position_id` (ячейки внутри позиции не режутся по границе страницы),
  CTE `cats` подтягивает `category_path`/`category_sort_path` один раз на
  встретившуюся категорию (не на позицию). Ответ — `columns` (дерево групп
  building_type/segment для `columnHelper.group`) + `items` (позиции с массивом
  ячеек, не map — чтобы `openapi-typescript` не выродил форму в
  `additionalProperties`).
- **DS-компоненты** `table`/`badge`/`card` — три слайса, реколор на переменных
  shadcn (foundation с прошлой задачи), первый нагруженный потребитель —
  сама матрица.
- **TanStack Router** — маршруты `/` (матрица) и `/design-system`; фильтры
  (`building_type_id`, `segment_id`, `q`, `offset`) — типизированный URL-контракт
  состояния экрана.
- **Хуки** `useMatrix`/`useBuildingTypes`/`useSegments` (TanStack Query) +
  MSW-обвязка тестов (`frontend/src/test/msw/`).
- **Чистые хелперы модели** `withSectionHeaders`/`cellFor` — вставляют
  строки-заголовки разделов на границе смены `category_path`, достают ячейку
  под нужный `segment_id` из массива позиции.
- **Экран `MatrixScreen`** — фильтры, группы колонок, дерево-заголовки разделов,
  рендер ячеек, пагинация «Вперёд»/«Назад» (клик двигает `offset` в URL).

## Развилки

Все зафиксированы в спеке r5, §«Развилки и решения»: server pivot vs плоский
`LIMIT/OFFSET` (§2.1), дерево колонок в payload (§2.2), плоские
строки-заголовки без сворачивания в v1 (§2.3), TanStack Router (§2.4), срез
DS ровно на `table`/`badge`/`card` (§2.5). Обоснования — там же.

## Находки (важно для будущих сессий)

- **react-refresh требует не-компонентные экспорты в отдельном файле.** Как и
  с `button` в прошлой задаче, `cva`-конфиг компонента (`badgeVariants`) не
  может жить в одном модуле с React-компонентом — Fast Refresh лечит только
  файлы, экспортирующие исключительно компоненты. Вынесено в
  [badge-variants.ts](../../frontend/src/components/ui/badge-variants.ts)
  (коммит `8248ca2`).
- **MSW + openapi-fetch: `listen()` — синхронно на верхнем уровне `setupFiles`,
  не внутри `beforeAll`.** `openapi-fetch` кеширует `globalThis.fetch`/`Request`
  один раз при `createClient()` (на импорте модуля). `setupFiles` целиком
  выполняются раньше самого тестового модуля — если бы `server.listen()` стоял
  в `beforeAll`, к моменту вызова он бы шёл уже после импорта `@/api/client`,
  и клиент навсегда закешировал бы непропатченный `fetch`: реальные запросы
  уходили бы мимо MSW. Зафиксировано комментарием в
  [frontend/src/test/setup.ts](../../frontend/src/test/setup.ts).
- **`schema.d.ts` — gitignored, регенерируется CI/`just types`.** Не коммитить
  вручную; расхождение с фактическим `openapi.json` ловится линтом/тайпчеком,
  не git diff.
- **Прогон `just ci` — обязателен целиком, не по частям.** На финале поймали
  на ровном месте: `frontend/src/components/ui/{badge,card,table,table.test}.tsx`
  прошли `lint`/`typecheck`/`test`, но не `prettier --check` (перенос длинных
  JSX-атрибутов/импортов) — тот же класс промаха, что уже фиксировался в
  [design-system-integration](2026-07-09-design-system-integration.md) и
  [test-system](2026-07-08-test-system.md). Починено отдельным коммитом
  (`ec1aa93`), семантика компонентов не тронута.

## Что отложено

Перенесено в [TECH_DEBT.md](../TECH_DEBT.md) (секция «Матрица перечня»):
сворачиваемое дерево разделов (конфликтует с серверной пагинацией — вне
объёма v1), материализация `category_path`/`category_sort_path` (если дерево
категорий вырастет или категории станут почти уникальны per-position),
подсветка совпавших ячеек при поиске по `q`, дебаунс поля поиска, косметика
групповой шапки над единственной колонкой при узком `segment_id`.

Из TECH_DEBT также снят закрытый пункт «Каталог компонентов» (секция
«Дизайн-система (foundation)» → «Компоненты») — `table`/`badge`/`card` собраны
этой веткой.

## Верификация

Полный `just ci` (types → lint → typecheck → test) зелёный:
- backend: `ruff check .` — 0 ошибок; `mypy app` — 0 ошибок;
  `pytest` — 108 passed (включая db-тесты `test_category_sort_path.py`,
  `test_matrix.py` на тест-ветке Neon).
- frontend: `eslint .` — 0 ошибок (1 некритичное предупреждение
  react-compiler про `useReactTable` — сторонняя библиотека, не наш код);
  `prettier --check` — чисто; `tsc --noEmit` — чисто; `vitest run` —
  13 passed (7 файлов, включая MSW-кейсы матрицы и серверную пагинацию —
  клик «Вперёд» двигает `offset` в URL).

Команды: `just ci` (из корня); точечно — `cd backend && uv run pytest
tests/db/test_category_sort_path.py tests/db/test_matrix.py -v`.
