# Дизайн: карточка вендора + кликабельные вендоры в каталоге

**Дата:** 2026-07-11
**Статус:** дизайн согласован с заказчиком (продуктовые решения + развилки O1–O4
подтверждены); развёрнут в спеку из design-заметки, ждёт ревью → план.
**Ветка:** `feat/vendor-card`
**Фаза:** 1 (ведение вендор-листов). Без проектов и светофора.

## Цель

Два связанных куска одного среза:

1. **Экран карточки вендора** (`/vendors/$vendorId`) — идентичность бренда,
   соглашение о сотрудничестве (простой тумблер), варианты написания (aliases),
   статус объединения, и обратный индекс **«Где разрешён»** с исключениями на
   уровне классов по правилу «граница легитимности — релиз».
2. **Кликабельные вендор-теги в каталоге** (`/matrix`): тег вендора в ячейке
   становится ссылкой на карточку.

Экран-список `/vendors` сейчас — заглушка «в разработке»; карточка делается
раньше списка, роутинг это допускает (список — отдельный срез позже).

Референс-макет: `vendor_card_final_release_rule.html` (тёмная тема; значения-заглушки).

## Терминология и подтверждённые факты схемы

Сверено по [0001_core_schema.sql](../../../backend/migrations/sql/0001_core_schema.sql)
и [0003_category_sort_path.py](../../../backend/migrations/versions/0003_category_sort_path.py).
Имена процитированы из DDL, не выдуманы.

| Понятие | Факт в схеме |
|---|---|
| **Вендор** | `vendor` ([:89](../../../backend/migrations/sql/0001_core_schema.sql#L89)): `id`, `name` (TEXT UNIQUE), `kind` (`vendor_kind`), `represents_id` (self-FK, nullable), `note`. **Нет** `deleted_at`, страны, `created_at`. Мягкого удаления вендора нет — дедуп через `represents_id`. |
| **Тип вендора** | enum `vendor_kind` = `manufacturer | supplier | other` ([:20](../../../backend/migrations/sql/0001_core_schema.sql#L20)). Локализуем **все три**: производитель / поставщик / прочее. |
| **Alias** | `vendor_alias` ([:99](../../../backend/migrations/sql/0001_core_schema.sql#L99)): `id`, `vendor_id` (FK ON DELETE CASCADE), `alias` (TEXT **UNIQUE глобально**). |
| **Соглашение (звезда)** | `agreement` ([:109](../../../backend/migrations/sql/0001_core_schema.sql#L109)) 1:N на вендора; `status` (`agreement_status`). Звезда = существует строка `status='active'` → функция `vendor_starred(int)` ([:122](../../../backend/migrations/sql/0001_core_schema.sql#L122)). `valid_until` — справочный, на звезду не влияет. |
| **`agreement_status`** | enum = `draft | active | expired | terminated` ([:21](../../../backend/migrations/sql/0001_core_schema.sql#L21)). «Выключено» = `terminated` (значение в enum есть — не выдумано). |
| **Аудит соглашений** | триггер `trg_agreement_audit` ([:157](../../../backend/migrations/sql/0001_core_schema.sql#L157)) пишет INSERT/UPDATE/DELETE в `agreement_change_log` с `changed_by DEFAULT current_app_user()`. ⇒ история тумблера пишется сама, если мутация идёт через `tx` (ставит `app.user`). |
| **Listing (живое)** | `listing` ([:168](../../../backend/migrations/sql/0001_core_schema.sql#L168)): строка `position × segment × vendor`; `status` ∈ `allowed | requirement | not_applicable | undefined`; мягкое удаление `deleted_at`/`deleted_by` **на уровне строки** ⇒ исключение вендора гранулярно до класса. Вьюха `listing_live` ([:407](../../../backend/migrations/sql/0001_core_schema.sql#L407)) уже фильтрует `deleted_at IS NULL`, но **не отдаёт `building_type_id`** — для «Где разрешён» джойним `segment.building_type_id` сами. |
| **Класс** | `segment` ([:56](../../../backend/migrations/sql/0001_core_schema.sql#L56)): принадлежит `building_type` (`building_type_id`), опц. `group_id`. Это «Делюкс/Премиум/Бизнес…». |
| **Стандарт** | `building_type` ([:37](../../../backend/migrations/sql/0001_core_schema.sql#L37)): `id`, `code`, `name`, `sort_order` (**есть** — `ORDER BY bt.sort_order` валиден). 3 строки (residential/office/social). Верхний уровень аккордеона «Где разрешён». |
| **Релиз** | `release` ([:309](../../../backend/migrations/sql/0001_core_schema.sql#L309)): `label` (TEXT, напр. «к Стандартам, 25.03.2026»), `status` ∈ `open | published | archived`, `effective_date`, `frozen_at`. **Номера версии нет** — релиз идентифицируется `label`. Снимок — `release_listing` ([:325](../../../backend/migrations/sql/0001_core_schema.sql#L325)), денормализован (`position_name`, `segment_name`, `vendor_name`, `vendor_starred` на момент выпуска). Один снимок = один `building_type` (через `release.building_type_id`). |
| **Порядок позиций** | `category_sort_path(p_id int) RETURNS int[]` (rev 0003) — тот же кураторский порядок, что в матрице; `ORDER BY` на `int[]` сортирует поэлементно. |
| **Бренд-ключ** | `coalesce(vendor.represents_id, vendor.id)`. В этом срезе «Где разрешён» смотрит **по самому вендору**, без разворота brand-key (см. O3). |

## Продуктовые решения (подтверждены заказчиком — не пересматривать)

1. **Соглашение — простой тумблер вкл/выкл.** Поля `signed_on/valid_until/doc_ref`
   в UI фазы 1 **не показываем**. «Выключить» ≠ удалить строку — это перевод
   активной строки в `terminated` (O1).
2. **Правило исключения (ключевое).** Зачёркнутый чип класса виден ТОЛЬКО если
   вендор **был в последнем `published`-релизе** этого стандарта (есть в
   `release_listing` со `status='allowed'`) **и** сейчас удалён из живого состояния
   (нет живой строки `listing` со `status='allowed'`). Черновичные опечатки
   («добавил и тут же удалил», в релиз не попадало) — **не показываются никак**.
   Релиз — граница легитимности.
3. **Без версий в строках.** «Где разрешён» показывает актуальное состояние; плашек
   «изд. vN» в строках нет. Идентификатор релиза (`label`) — только в тултипе
   зачёркнутого чипа и в тихой легенде внизу блока.
4. **Терминология:** «Соглашение о сотрудничестве» (не «допуск»), «релиз»
   (не «заморозка»). UI только на русском.

## Где живёт логика (тест ТЗ §6)

- **Правило исключения** — чистая вычислимая проекция над снимком релиза + живым
  `listing`. Не инвариант записи (ничего не ограничивает при write), но по золотому
  правилу №2 «не дублировать вычислимое в коде» — держим **одной истиной в SQL**:
  set-returning функция `vendor_where_allowed(p_vendor_id int)`. API читает готовые
  строки, правило в коде не повторяет.
- **Сборка дерева** (стандарт → позиции → чипы) из плоских строк функции —
  презентация, не бизнес-логика. → **бэкенд-роутер** (тонкая вложенность, без
  вычислений).
- **Тумблер соглашения / alias CRUD** — процесс записи, не инвариант. → **бэкенд**
  пишущими эндпоинтами через `tx`; аудит соглашения делает триггер БД.

## Правило исключения — SQL (референс)

Новая функция чистым SQL (Alembic-ревизия поверх `0004`; базовые `0001/0002`
неизменны — CLAUDE.md §5). Возвращает плоский упорядоченный набор; порядок позиций —
`category_sort_path` (как в матрице), классов — `segment.sort_order`.

```sql
CREATE FUNCTION vendor_where_allowed(p_vendor_id int)
RETURNS TABLE (
    building_type_id   int,
    building_type_name text,
    position_id        int,
    position_name      text,
    segment_id         int,
    segment_name       text,
    state              text,   -- 'allowed' | 'excluded'
    release_label      text    -- для 'excluded': label текущего релиза; иначе NULL
) LANGUAGE sql STABLE AS
$$
WITH current_release AS (          -- последний published-релиз на каждый тип
    SELECT DISTINCT ON (building_type_id) id, building_type_id, label
    FROM release
    WHERE status = 'published'
    ORDER BY building_type_id,
             effective_date DESC NULLS LAST,
             frozen_at      DESC NULLS LAST,
             id             DESC           -- PK-страховка детерминизма (как в дашборде)
),
released AS (                      -- вендор в снимке этого релиза (allowed)
    SELECT cr.building_type_id, rl.position_id, rl.segment_id, cr.label
    FROM current_release cr
    JOIN release_listing rl ON rl.release_id = cr.id
    WHERE rl.vendor_id = p_vendor_id AND rl.status = 'allowed'
      AND rl.position_id IS NOT NULL AND rl.segment_id IS NOT NULL
),
live AS (                          -- вендор жив сейчас (allowed)
    SELECT seg.building_type_id, l.position_id, l.segment_id
    FROM listing l
    JOIN segment seg ON seg.id = l.segment_id
    WHERE l.vendor_id = p_vendor_id AND l.status = 'allowed'
      AND l.deleted_at IS NULL
),
keys AS (
    SELECT building_type_id, position_id, segment_id FROM live
    UNION
    SELECT building_type_id, position_id, segment_id FROM released
)
SELECT bt.id, bt.name, pos.id, pos.name, seg.id, seg.name,
       CASE WHEN lv.position_id IS NOT NULL THEN 'allowed' ELSE 'excluded' END,
       CASE WHEN lv.position_id IS NULL THEN rl.label ELSE NULL END
FROM keys k
JOIN building_type bt ON bt.id  = k.building_type_id
JOIN position      pos ON pos.id = k.position_id
JOIN segment       seg ON seg.id = k.segment_id
LEFT JOIN live     lv ON (lv.building_type_id, lv.position_id, lv.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
LEFT JOIN released rl ON (rl.building_type_id, rl.position_id, rl.segment_id)
                       = (k.building_type_id, k.position_id, k.segment_id)
ORDER BY bt.sort_order,
         category_sort_path(pos.category_id), pos.sort_order, pos.name,
         seg.sort_order, seg.name;
$$;
```

Правило исключения в терминах кейсов (это и есть тест-матрица):
- **(а)** есть в релизе **и** жив → `state='allowed'` (обычный чип).
- **(б)** есть в релизе, удалён из живого → `state='excluded'` (зачёркнутый, тултип с `label`).
- **(в)** не был в релизе, добавлен в черновике и удалён → нет ни в `released`, ни в `live` → **строки нет**.
- **(г)** не был нигде → строки нет.

> **brand-key НЕ разворачиваем** (O3): фильтр строго `vendor_id = p_vendor_id`.
> Листинги представляемых брендов на карточке владельца — TECH_DEBT.

## Контракт API

Новый роутер `routers/vendors.py` (prefix `/vendors`). Регистрация — добавить в
[`routers/__init__.py`](../../../backend/app/routers/__init__.py); [`main.py:56`](../../../backend/app/main.py#L56)
подключит автоматически. Схемы — в [`schemas/__init__.py`](../../../backend/app/schemas/__init__.py)
(там сейчас единый файл). `just types` после бэкенда.

### Чтение (два эндпоинта — раздельно)

Разделяем, потому что «Где разрешён» потенциально крупный и независимо
кэшируемый/ленивый, а шапка мала и нужна всегда.

```
GET /vendors/{id}              -> VendorCard      # шапка + note + aliases + represents
GET /vendors/{id}/where-allowed -> WhereAllowed    # дерево стандарт→позиции→классы
```

```python
class VendorAlias(BaseModel):
    id: int
    alias: str

class VendorRepresents(BaseModel):        # если represents_id задан
    id: int
    name: str

class VendorCard(BaseModel):
    id: int
    name: str
    kind: str                              # локализация имени — на фронте
    note: str | None
    starred: bool                          # vendor_starred(id)
    represents: VendorRepresents | None    # владелец бренда (ссылка на его карточку)
    represented_count: int                 # count(*) FROM vendor WHERE represents_id = id
    aliases: list[VendorAlias]

class WhereAllowedChip(BaseModel):
    segment_id: int
    segment_name: str
    state: str                             # 'allowed' | 'excluded'
    release_label: str | None              # для 'excluded' — тултип

class WhereAllowedPosition(BaseModel):
    position_id: int
    position_name: str
    chips: list[WhereAllowedChip]

class WhereAllowedStandard(BaseModel):
    building_type_id: int
    building_type_name: str
    position_count: int
    positions: list[WhereAllowedPosition]

class WhereAllowed(BaseModel):
    standards: list[WhereAllowedStandard]  # вложение из плоских строк vendor_where_allowed
```

- `GET /vendors/{id}`: 404 если вендора нет. `starred` = `vendor_starred(id)`;
  `represented_count` = обратный счётчик; `represents` — джойн по `represents_id`.
- `GET /vendors/{id}/where-allowed`: роутер читает `vendor_where_allowed(:id)`
  (строки уже упорядочены) и **вкладывает** в `standards[].positions[].chips[]`,
  сохраняя порядок. `position_count` = число позиций стандарта. Логику не считает.
- Оба — `dependencies=[Depends(require_user)]` + `conn = Depends(read_conn)`
  (паттерн `releases.py`).

### Запись (мутации — отдельный слайс)

Все — `Depends(require_admin)` + `Depends(tx)` (tx ставит `app.user` bind-параметром;
аудит соглашения подпишется логином админа). Инварианты БД (уникальность alias) →
ловим `DBAPIError` → `409` (паттерн `releases.py` freeze).

```
PUT    /vendors/{id}/agreement   body {active: bool}   -> {starred: bool}
POST   /vendors/{id}/aliases     body {alias: str}      -> VendorAlias      (409 при дубле)
DELETE /vendors/{id}/aliases/{alias_id}                 -> 204
```

**Тумблер соглашения (O1) — асимметрично, инвариант «одна активная строка»:**
- `active=true`: если активная строка уже есть → **no-op** (UPDATE **не** выполняем —
  иначе пустой `UPDATE … SET status='active' WHERE status='active'` дёрнет триггер и
  засорит `agreement_change_log`); иначе — **всегда** `INSERT (vendor_id, status='active')`.
  **Историю не реанимируем**: `expired`/`terminated`-строку в `active` не флипаем —
  иначе её `signed_on/valid_until/doc_ref` исторического договора «оживут» как
  действующие. Включение = новая строка, не воскрешение старой.
- `active=false`: `UPDATE agreement SET status='terminated' WHERE vendor_id=:id AND status='active'`.
- Ответ — актуальный `vendor_starred(id)`. Вторую историю строками **не городим** —
  чередование вкл/выкл фиксирует `agreement_change_log` (триггер). `terminated` в enum есть.

## Фронтенд

- **Роут:** добавить динамический `/vendors/$vendorId` в
  [router.tsx](../../../frontend/src/router.tsx) (code-based дерево; `routeTree`
  по-прежнему экспортируется для memory-router в тестах). `/vendors` (список) —
  остаётся заглушкой `VendorsScreen`.
- **Экран** `screens/vendors/VendorCardScreen.tsx` + `model.ts` (чистые хелперы:
  локализация `kind`, текст легенды/тултипа; дерево уже приходит вложенным из API).
  Структура — как `screens/matrix/` и `screens/dashboard/`.
- **Данные:** хуки в [queries.ts](../../../frontend/src/api/queries.ts) поверх
  типизированного клиента: `useVendor(id)`, `useVendorWhereAllowed(id)` (чтение);
  `useToggleAgreement(id)`, `useAddAlias(id)`, `useRemoveAlias(id)` (мутации,
  инвалидируют `useVendor`). Формы — из OpenAPI → `schema.d.ts` (`just types`).
- **Блоки карточки (сверху вниз):**
  1. **Шапка:** имя; бейдж `kind` (локализованный); бейдж-пилюля «⭐ соглашение»
     (виден при `starred`); статус бренда — «самостоятельный бренд» (`represents=null`)
     или «представляет: <имя>» (`<Link>` на карточку владельца); тумблер «Соглашение»;
     меню `⋯` (disabled-плейсхолдеры).
  2. **Заметка** (`note`) — рендерится **только если непустая**.
  3. **Варианты написания** (`aliases`): чипы с удалением (×) и «+ вариант»
     (инлайн-добавление); валидация — alias глобально уникален (409 → тост).
  4. **Бренд и объединение:** статус + счётчик «N брендов представлены этим»
     (`represented_count`, обратные ссылки — плейсхолдер/скрыт, если 0); кнопка
     «Объединить» — **disabled + «в разработке»** (O2, поток — отдельный срез).
  5. **«Где разрешён»** (аккордеон по стандартам): свёрнутый стандарт показывает
     `position_count`; внутри — позиции, у каждой чипы классов:
     - обычный чип = `state='allowed'`;
     - зачёркнутый приглушённый чип = `state='excluded'`, с тултипом
       **«Был в релизе „<release_label>“, исключён в текущем черновике»** (длинный
       `label` — усечь/перенести, деталь реализации);
     - классы без строки не показываются.
     Внизу — тихая **легенда** («~~класс~~ — был в последнем релизе, исключён ·
     показано текущее состояние стандартов»).
- **DS-примитивы (новые, через `shadcn add`, реколор через переменные shadcn, свой
  vitest):** `switch` (тумблер соглашения), `accordion` («Где разрешён»). `tooltip`,
  `badge`, `card` — **уже есть**, переиспользуем. Зачёркнутый чип — `badge` +
  `line-through`/`text-muted-foreground`/dashed `border` на **существующих** токенах;
  новых цвет-токенов **не заводим** (в отличие от дашборда — `warning` не нужен).
- **Локализация — только русская. Mobile-first** (аккордеон и чипы — от узкого к
  широкому; `flex-wrap` чипов, `truncate`/`min-w-0` длинных имён; тач-цели ≥ 40px).

## Кликабельные вендоры в каталоге

- **Бэкенд не трогаем:** `vendor_id` уже в payload ячейки матрицы
  ([listings.py:186](../../../backend/app/routers/listings.py#L186)) — id не парсим из текста.
- В [columns.tsx](../../../frontend/src/screens/matrix/columns.tsx) `renderCell` —
  оборачиваем `Badge` вендора в `<Link to="/vendors/$vendorId" params={{ vendorId: String(v.vendor_id) }}>`.
- Тег остаётся **визуально тегом** (не подчёркнутая ссылка): hover — лёгкое усиление
  рамки/фона на семантических токенах, `cursor-pointer`, focus-visible-кольцо
  (`--ring`). Доступность: это **ссылка**, не кнопка.
- Кликабельны **только вендор-теги** (`status='allowed'`). Рендер требований
  (`requirement`/`spec_text`) и прочерков (`—`) не меняем — они не кликабельны.

## Тесты (red → green)

**Backend** (`pytest` + фабрики, маркер `db` на тест-ветке Neon):
- `vendor_where_allowed` — **4 кейса правила** (а/б/в/г из §Правило исключения):
  в релизе+жив → `allowed`; в релизе+удалён → `excluded` (+ `release_label`);
  черновая опечатка (не в релизе, добавлен и удалён) → строки нет; не был нигде →
  строки нет. Плюс: детерминизм «последнего релиза» при равных `effective_date`
  (страховка `id`); порядок позиций по `category_sort_path`.
- Тумблер соглашения: вкл на вендоре без строк → INSERT active, `starred=true`;
  выкл → активная в `terminated`, `starred=false`; повторное вкл (после выкл) →
  **новая** active-строка, старый `terminated`/`expired` **не** реанимируется
  (проверить: у вендора с последней `expired`-строкой вкл создаёт новую active, а не
  флипает expired); **вкл на уже активном → no-op**: UPDATE не выполняется, строк в
  `agreement_change_log` **не прибавляется**. **Аудит**: изменения пишутся с
  `changed_by = app.user` (мутация через `tx`).
- Alias: добавление; **глобальная уникальность** (дубль → 409); удаление.
- api-тесты через ASGI-`client`: форма `GET /vendors/{id}` (represents, обратный
  счётчик, starred) и `/where-allowed` (вложенное дерево, `position_count`); 404 на
  несуществующего; **RBAC** — `viewer` читает; мутации требуют `admin` (viewer → 403).

**Frontend** (Vitest + MSW под сгенерированную схему):
- рендер блоков карточки; **скрытие `note`** при пустом; **пилюля соглашения** скрыта
  при `starred=false`; «представляет» — ссылка на владельца.
- «Где разрешён»: дерево стандартов/позиций/чипов; **зачёркнутый чип** имеет тултип и
  aria-описание; свёрнутый стандарт показывает `position_count`.
- Мутации: тумблер зовёт `useToggleAgreement` и инвалидирует карточку; alias ×/+ ;
  дубль alias → тост об ошибке.
- **Матрица:** клик по тегу вендора ведёт на `/vendors/$id` (memory-router);
  ячейки-требования и прочерки — **не** кликабельны; focus-visible на теге.

## Развилки (решения заказчика, помечены для ревью)

| # | Развилка | Решение (подтверждено) |
|---|----------|------------------------|
| O1 | Механика тумблера соглашения | **Асимметрично**, инвариант «одна активная строка»: выкл = флип активной в `terminated`; вкл = no-op если активна, иначе **INSERT** новой `active` (историю `expired`/`terminated` не реанимируем). Аудит — триггер, вторую историю не городим |
| O2 | Поток «Объединить» | **Заглушка** (disabled + «в разработке»); полноценное объединение (перенос listing) — отдельный срез |
| O3 | Листинги представляемых брендов на карточке владельца | **Не показывать**; агрегацию по brand-key — в TECH_DEBT |
| O4 | Тултип зачёркнутого чипа | **С `release.label`**: «Был в релизе „<label>“, исключён в текущем черновике»; длинный label — усечь (деталь реализации) |

## Порядок слайсов (бисектабельно, `just ci` зелёный на каждом)

1. **Миграция + правило:** Alembic-ревизия (поверх `0004`, чистый SQL) с функцией
   `vendor_where_allowed`; db-тесты — 4 кейса правила + детерминизм + порядок.
2. **Бэкенд чтение:** роутер `vendors` — `GET /vendors/{id}` + `/where-allowed`
   (+ схемы, регистрация, вложение дерева) + db/api-тесты; `just types`.
3. **Фронт карточка (read-only):** роут `/vendors/$vendorId`; `VendorCardScreen` +
   `model.ts` + `useVendor`/`useVendorWhereAllowed`; DS `accordion` (+ `switch`
   отрисован disabled до слайса 5); блоки шапка/note/aliases(показ)/бренд/«Где
   разрешён» с зачёркнутыми чипами + тултип + легенда; Vitest/MSW.
4. **Кликабельность матрицы:** `Link` вокруг вендор-тега + hover/focus на токенах;
   тесты навигации и некликабельности требований. (Мал и независим.)
5. **Мутации:** бэкенд `PUT /agreement` + alias `POST`/`DELETE` (`tx`, `require_admin`)
   + db/api-тесты; фронт — включаем тумблер и alias ×/+ (`useToggleAgreement`/
   `useAddAlias`/`useRemoveAlias` + инвалидация) + тесты; `just types`.
6. **Финализация:** `just ci` зелёный; devlog; CLAUDE.md §5 (карточка вендора,
   `/vendors/$vendorId`, карта репо: `screens/vendors/`, роутер `vendors`) + TECH_DEBT.

## Вне объёма

- Список `/vendors` (data-table) — отдельный срез.
- Поток объединения дублей (перенос listing, установка `represents_id`) — O2, отдельно.
- Листинги представляемых брендов на карточке владельца — O3, TECH_DEBT.
- История соглашений и `agreement_change_log` в UI — не показываем.
- Поля `signed_on/valid_until/doc_ref` соглашения в UI — не показываем (тумблер).
- Проекты, светофор, проверка соответствия (фаза 2).
- Импорт/экспорт Excel, админ-редактирование перечня.
- Дублирование бизнес-логики БД в коде; ORM; правка базовых `0001/0002`.

## TECH_DEBT (внести при реализации)

- **Агрегация по brand-key на карточке владельца** (O3) — показывать листинги
  представляемых брендов объединённо; решать вместе с потоком объединения (O2).
- **Поток «Объединить»** (O2) — из заглушки в полноценный диалог + перенос
  listing-строк объединяемого вендора.
- **Ленивое раскрытие «Где разрешён»** — если у вендора сотни позиций, грузить дерево
  по стандарту лениво (сейчас — один ответ целиком).
