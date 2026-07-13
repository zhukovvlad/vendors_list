# Смена региона Neon (us-east-1 → eu-central-1)

Перенос БД проекта из **AWS us-east-1 (Вирджиния)** в **AWS eu-central-1 (Франкфурт)**.
Мотив — латентность: RTT с машины разработчика (регион +0300) измерен как **119 мс
(us-east-1) против 34 мс (eu-central-1) — ~3.5× ниже** (TCP-connect, прокси через
`s3.<region>.amazonaws.com` совпал с реальным Neon-эндпоинтом в пределах ~2 мс). Выигрыш
системный: локальные db-тесты и — главное — отклик боевого приложения для пользователей
в KZ (−85 мс на каждый запрос к БД).

> **Регион Neon-проекта неизменяем.** Сменить локацию существующего проекта in-place
> нельзя — только создать НОВЫЙ проект в целевом регионе и переключиться на него.

Затрагивает две строки в `backend/.env` (`DATABASE_URL`, `DATABASE_URL_TEST`) и секрет CI
`NEON_PROJECT_ID`. Расширений PostgreSQL в схеме нет (проверено:
`grep -i "create extension" backend/migrations/sql/` пуст).

---

## Основной путь (проект в разработке): снести и развернуть заново

Пока нет боевых данных, которые нельзя воссоздать, — **не переносим данные, а строим БД
заново из источников истины**: схему собирают миграции, стартовый датасет возвращает сид.
Никакого dump/restore, окна cutover и сверки парности.

> ⚠️ **Этот путь стирает всё, что не воспроизводится из сида:** ручные переименования
> вендоров, соглашения, алиасы, правки разрешений через режим редактирования карточки.
> Плюс `vendor.id` не стабильны между прогонами сида (память проекта). Если такие правки
> есть и они нужны — см. раздел «Позже: сохранение боевых данных» ниже.

### Шаги

1. **Создать новый проект в eu-central-1.**
   Neon-консоль или `neonctl projects create --region-id aws-eu-central-1 --name vendors-eu`.
   Зафиксировать **новый `project_id`** (формат `autumn-wave-...`, это НЕ `ep-...` endpoint id).

2. **Привести ветки к ожиданиям CI.**
   Дефолтная primary-ветка нового проекта обычно `main` — **переименовать в `production`**
   (CI ветвит тест-БД от `parent_branch: production`,
   [.github/workflows/ci.yml:45](../../.github/workflows/ci.yml)). Создать ветку `test`
   (data+schema) от `production` — под `DATABASE_URL_TEST`.

3. **Обновить конфиг.**
   - `backend/.env`:
     - `DATABASE_URL` → **pooled** эндпоинт `production`-ветки нового проекта (приложение
       ходит через пулер; `app/db.py` рассчитан на PgBouncer transaction pooling).
     - `DATABASE_URL_TEST` → строка ветки `test` нового проекта.
   - Секрет CI `NEON_PROJECT_ID` (GitHub → Settings → Secrets) → новый `project_id`.
     `NEON_API_KEY` — если проект под тем же аккаунтом, ключ прежний.

4. **Построить схему миграциями.**
   ```bash
   just migrate        # боевая (production-ветка) — head 0006
   just migrate-test   # тест-ветка Neon
   just migrate-current # sanity: head = 0006_ensure_open_release
   ```

5. **Вернуть стартовый датасет (опционально).**
   ```bash
   just seed --yes --freeze   # 3 перечня Excel в live + 3 published-издания (генезис)
   ```
   Пропустить, если нужна пустая БД. После сида проверить дашборд
   (`curl -s "$APP_URL/api/dashboard"`): при полном сиде — releases=3, drafts=0
   (positions/цифры зависят от текущих исходников; сверять с прошлым прогоном не обязательно —
   БД строится с нуля).

6. **Проверка вживую + RTT.**
   ```bash
   curl -s "$APP_URL/api/dashboard" | python -m json.tool | head   # приложение читает
   # новый RTT — ожидаем ~34 мс вместо ~119
   cd backend && uv run python - <<'PY'
   import socket, time
   h="s3.eu-central-1.amazonaws.com"; b=None
   for _ in range(6):
       s=socket.socket(); s.settimeout(5); t=time.perf_counter()
       s.connect((h,443)); dt=(time.perf_counter()-t)*1000
       b=dt if b is None else min(b,dt); s.close()
   print(f"eu-central-1 RTT ~ {b:.1f} ms")
   PY
   ```
   Прогнать `just ci` — backend-сьют против новой тест-ветки должен пройти и стать ещё
   быстрее (session-scope + низкий RTT). Дождаться зелёного CI на пуше (эфемерная ветка
   создаётся от `production` нового проекта).

7. **Удалить старый проект** (us-east-1) — после подтверждения, что новый работает.

### Чек-лист

- [ ] Новый проект в **eu-central-1** (подтвердить по хосту `...eu-central-1.aws.neon.tech`).
- [ ] Primary-ветка переименована `main` → **`production`**; создана ветка `test`.
- [ ] Обновлены **обе** строки в `.env` + секрет CI `NEON_PROJECT_ID`.
- [ ] `just migrate` **и** `just migrate-test` прогнаны; `just migrate-current` = `0006`.
- [ ] `DATABASE_URL` — **pooled** эндпоинт (не direct); `statement_cache_size=0` в
      `app/db.py` уже есть, менять не нужно.
- [ ] Приложение читает/пишет; RTT ~34 мс.
- [ ] CI (раннеры в US) к Neon в EU станет чуть медленнее (десятки мс) — ожидаемо, некритично.
- [ ] Старый проект удалён.

---

## Позже: сохранение боевых данных (после запуска)

Когда в БД появятся данные, которые нельзя воссоздать из сида (реальные проекты,
ручные правки), смена региона превращается в перенос данных через dump/restore.

**Инструменты:** клиентские `pg_dump`/`pg_restore` версии **≥ 18** (сервер Neon = PG 18);
для dump/restore — **ПРЯМОЙ (direct), не pooled** эндпоинт (пулер PgBouncer в transaction
mode ломает эти утилиты).

```bash
# 1) снять эталон со старой боевой (для сверки парности)
just migrate-current   # ожидаем 0006
psql "$DATABASE_URL_DIRECT_OLD" -c "SELECT
  (SELECT count(*) FROM listing) AS listing_all,
  (SELECT count(*) FROM listing WHERE deleted_at IS NULL) AS listing_live,
  (SELECT count(*) FROM vendor) AS vendors,
  (SELECT count(*) FROM release) AS releases;"

# 2) пауза записи в старую боевую (консистентный dump)

# 3) DUMP (direct старого) → RESTORE (direct нового)
pg_dump "$DATABASE_URL_DIRECT_OLD" --format=custom --no-owner --no-privileges \
  --file=vendors_us_east_1.dump
pg_restore --no-owner --no-privileges --exit-on-error \
  --dbname="$DATABASE_URL_DIRECT_NEW" vendors_us_east_1.dump

# 4) сверка парности: счётчики нового == эталон; alembic_version доехал → migrate-current = 0006
# 5) cutover (.env + секрет CI), перезапуск приложения
# 6) старый проект держать живым 1-2 недели как страховку, затем удалить
```

Полный dump переносит схему (построенную миграциями), данные, sequence-значения и
`alembic_version` как есть. Триггеры/`listing_cell_chk` — как объекты схемы; restore льёт
данные через COPY, не вызывая бизнес-логику API, поэтому аудит/`deleted_by` сохраняются.

**Откат** (пока старый проект жив): вернуть старые URL в `.env` + секрет CI, перезапустить.
Записи, сделанные в новом проекте после cutover, при откате не переносятся — учитывать при
выборе окна.
