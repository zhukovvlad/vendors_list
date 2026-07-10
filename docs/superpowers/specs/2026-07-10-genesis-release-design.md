# Дизайн: «Генезис-издание» из сида

**Дата:** 2026-07-10
**Статус:** утверждён к реализации
**Бриф-исток:** [genesis-release-KICKOFF.md](../genesis-release-KICKOFF.md)

## Цель

Превратить вчера засеянный live-перечень (`just seed`, 3 Excel, 13 244 строки
в `listing`) в **3 базовых `published`-издания** — по одному на building_type
(жилой / офис / соц). Сейчас данные лежат только в живом слое `listing` и не
обёрнуты ни в один `release`, поэтому дашборд показывает Позиции = 0, Издания = 0.
После генезиса дашборд отражает реальность.

## Ключевая находка (переопределяет форки брифа)

Механика фиксации **уже существует и покрыта тестами** — писать её не нужно:

- **Флаг `--freeze` у сида** ([loader.py:325-344](../../../backend/app/seed/loader.py#L325-L344)):
  для каждого building_type создаёт `release(status='open')` с
  `label='к Стандартам, {дата}'` и `effective_date`, затем зовёт `freeze_release`.
- **API `POST /releases/{id}/freeze`** ([releases.py:51](../../../backend/app/routers/releases.py#L51)),
  `GET /releases`, `GET /releases/{id}/listing` — admin, через `tx` (аудит).
- **Функция `freeze_release`** в БД ([0001_core_schema.sql:360-402](../../../backend/migrations/sql/0001_core_schema.sql#L360-L402)).

Следствие: генезис — **операционный прогон существующего пути**, а не новая логика.
Нового продакшн-кода нет (миграции / API / парсер не трогаем).

## Решения по форкам (утверждены заказчиком)

| Форк | Решение | Обоснование |
|------|---------|-------------|
| Метод фиксации | Пере-прогон `just seed --yes --freeze` | Ноль нового кода, полностью протестированный путь. Reset+reseed допустим: dev-окружение, данные воспроизводимы. |
| 1. Чистить артефакты имён (кавычки) до freeze | **Нет, фиксируем как есть** | Парсер сознательно не срезает кавычки («нормализация в источнике, не в скрипте», [devlog](../../devlog/2026-07-09-excel-seed-import.md)). Генезис — базовая точка; неизменяемость не пугает, правки — в источнике/админ-контуре → перевыпуск. |
| 2. Где живёт логика фиксации | Сид-флаг `--freeze` (не API) | Инвариант уже в БД (`freeze_release`); процесс запуска — в бэкенде. §6 админ-контур не строим. |
| 3. Аудит записи | `app.user='seed'` (дефолт CLI) | `execute()` ставит `set_config('app.user','seed',local)` bind-параметром до записи; `freeze_release` получает `author='seed'`. |
| 4. label / effective_date | `label='к Стандартам, 2026-03-25'`, `effective_date=2026-03-25` | Дата из имён файлов `temp/` (regex `\d{4}-\d{2}-\d{2}`); все 3 файла датированы 2026-03-25. Задаётся существующим кодом сида. |
| 5. Open-черновик после генезиса | **Нет** | `seed --freeze` оставляет 3 published, 0 open. Новый open создастся при старте редактирования (будущий админ-контур §6). |
| 6. Идемпотентность | Через `_reset` | `seed --yes --freeze` сперва DELETE live-таблиц → повторный прогон всегда даёт ровно 3 издания, без дублей. |

## Что делает `just seed --yes --freeze`

Существующий код ([loader.py:223-344](../../../backend/app/seed/loader.py#L223-L344)):

1. `set_config('app.user','seed', local)` — идентичность аудита (золотое правило #3).
2. **Guard** `_guard_no_projects`: отказ, если в `compliance.project` +
   `compliance.project_selection` есть строки. Сейчас 0 → проходит без `--force`.
3. `_reset` → re-insert: DELETE public-таблиц в FK-безопасном порядке
   (`_RESET_ORDER`), затем batch-`executemany` вставляет
   категории → позиции → вендоры → соглашения → листинги из 3 Excel
   (идентично текущему live-состоянию).
4. Для каждого присутствующего building_type:
   `INSERT release(building_type_id, label, effective_date, status='open')`
   → `SELECT freeze_release(release_id, 'seed')`. Функция копирует живой
   `listing` (по типу, не soft-deleted) в неизменяемый снимок `release_listing`
   с денормализацией подписей (`category_path`, `position_name`, `vendor_name`,
   `vendor_starred` на момент фиксации), ставит `status='published'` + `frozen_at`.
5. Итог: **3 published-издания, 0 open-черновиков.**

## Раннбук исполнения

Реализация — не написание кода, а исполнение и верификация по шагам.

1. **Pre-flight:** `just seed-verify` (dry-run + калибровка §19, без БД) —
   убедиться, что парсер сходится со счётчиками. Подтвердить: в `temp/` ровно
   3 файла по маскам `*жилые*`/`*офисные*`/`*социальные*` (проверено 2026-07-10).
2. **Grounding (before):** зафиксировать до-состояние **живым запросом**
   (не по памяти — иначе after-сравнение недоказуемо):
   `release=0`, `release_listing=0`, `live listing=13 244`,
   `dashboard_summary`: positions_active=0, releases_published=0, drafts_open=0,
   vendors_total=898, vendors_with_agreement=117.
   Дополнительно снять **отпечаток last-write** — `MAX(updated_at)` и
   `array_agg(DISTINCT updated_by)` по `listing` и `vendor`. Если максимум = времени
   вчерашнего сида, а `updated_by` = `{seed}`, значит ручных правок после сида не
   было и деструктивный reset ничего не сотрёт молча. Guard `_guard_no_projects`
   проверяет только `compliance.project*` — он НЕ ловит ручные правки live-слоя,
   поэтому отпечаток закрывает этот зазор.
3. **Execute:** `just seed --yes --freeze` против боевого Neon.
   **Только по явному go-ahead заказчика** (reset+reseed live-слоя, необратимо
   на месте). Бэкап-ветку Neon НЕ делаем (dev, данные воспроизводимы — решение
   заказчика: «не плодить сущности, могу безопасно снести»).
4. **Post-verify (доказательство до заявления «готово»):**
   - `release`: ровно 3 строки, все `status='published'`,
     `effective_date=2026-03-25`, `frozen_at IS NOT NULL`, по одному на каждый
     building_type.
   - `release_listing`: непусто по каждому `release_id`. **Строгий инвариант**
     (не «сопоставимо»): `freeze_release` копирует все живые строки типа без
     фильтра по статусу (`WHERE seg.building_type_id = v_bt AND l.deleted_at IS NULL`,
     INNER JOIN по `position`/`segment` — оба `NOT NULL`), каждая живая строка
     принадлежит ровно одному building_type. Значит должно выполняться
     **точное равенство**:
     `SUM(release_listing по 3 изданиям) == COUNT(listing WHERE deleted_at IS NULL)`
     ( = 13 244, раз soft-delete-ов нет). Расхождение сумм = реальная ошибка
     (осиротевший building_type сегмента или неучтённый soft-delete) → стоп.
   - `dashboard_summary`: `positions_active > 0`, `releases_published=3`,
     `drafts_open=0`, `vendors_total`/`vendors_with_agreement` без изменений
     (~898 / ~117).
   - Опционально: `GET /dashboard` и `GET /releases` возвращают то же
     (сквозная проверка API).
5. **Документирование:** девлог `docs/devlog/2026-07-10-genesis-release.md`
   (замер, before/after, находка про существующий `--freeze`; **явно
   зафиксировать факт: `vendor.id` (и прочие serial) не стабильны между
   прогонами сида — reset через `DELETE`, не `TRUNCATE RESTART IDENTITY`, id
   после reseed поедут вверх; сейчас безопасно, т.к. на них никто не ссылается
   (0 проектов, 0 прежних изданий), но узнать о захардкоженном id лучше сейчас**);
   обновить CLAUDE.md §5 (издания зафиксированы, БД на 0004); обновить память
   ([[genesis-release-next]] → исполнено); закрыть KICKOFF.

## Риски и митигации

- **Destructive reset** — безопасно: 0 проектов в `compliance` (guard) + отпечаток
  last-write на шаге Grounding доказывает, что ручных правок после сида не было
  (а не предполагает это) → повторный прогон воспроизводит идентичный live-слой.
- **Идемпотентность** — `_reset` перед вставкой гарантирует ровно 3 издания
  при любом числе прогонов (форк 6).
- **Артефакты кавычек в снимке** — приняты (форк 1); правятся в источнике /
  будущем админ-контуре с перевыпуском издания.
- **Мутация боевой БД** — гейт на явное подтверждение заказчика на шаге Execute.

## Тестирование

Нового продакшн-кода нет → новых автотестов нет. Механику уже сторожат:

- `backend/tests/db/test_freeze_release.py` — функция БД (копирует + публикует,
  повторный freeze → исключение).
- `backend/tests/api/test_releases.py` — API (freeze, 409 на unknown, 403 viewer).
- `backend/tests/db/test_seed_loader.py` — loader, включая freeze-ветку.

`just ci` остаётся зелёным (код не тронут). Верификация генезиса —
рантайм-доказательства (post-verify запросы шага 4), не новые автотесты.

## Вне scope

- Интерактивный импорт/экспорт (§5), админ-редактирование (§6), эндпоинт
  создания издания (`POST /releases`), чистка имён вендоров, светофор §4.
