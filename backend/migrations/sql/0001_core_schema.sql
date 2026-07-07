-- ============================================================================
--  Vendor list (Перечень производителей) — схема БД, PostgreSQL
--  АО "МР Групп" — жилые / офисные(+ТРЦ) / социальные объекты
--
--  Три смысловых блока:
--    1. Справочники      — типы объектов, классы (с группами), дерево разделов,
--                          позиции, вендоры (+синонимы), реестр соглашений.
--    2. Живое состояние  — LISTING (текущая правда) + append-only CHANGE_LOG.
--    3. Издания          — RELEASE + неизменяемые снимки RELEASE_LISTING.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
--  Перечислимые типы
-- ---------------------------------------------------------------------------
-- Требования ("Россия", ГОСТ, "по согласованию") выражаются ТОЛЬКО через
-- listing_status='requirement' + spec_text — поэтому 'country'/'standard'
-- в типах вендора нет (см. ревью: одно представление вместо двух).
CREATE TYPE vendor_kind     AS ENUM ('manufacturer', 'supplier', 'other');
CREATE TYPE agreement_status AS ENUM ('draft', 'active', 'expired', 'terminated');
-- статус ячейки: разрешён вендор / неприменимо ("-") / не задано (пусто) / требование ("Россия", ГОСТ, "по согласованию")
CREATE TYPE listing_status  AS ENUM ('allowed', 'not_applicable', 'undefined', 'requirement');
CREATE TYPE release_status  AS ENUM ('open', 'published', 'archived');
CREATE TYPE change_action   AS ENUM ('insert', 'update', 'delete');

-- кто внёс правку: приложение ставит SET app.user = '...'; иначе — роль БД
CREATE FUNCTION current_app_user() RETURNS text
  LANGUAGE sql STABLE AS
$$ SELECT coalesce(nullif(current_setting('app.user', true), ''), current_user); $$;


-- ===========================================================================
--  1. СПРАВОЧНИКИ
-- ===========================================================================

CREATE TABLE building_type (
    id          serial PRIMARY KEY,
    code        text NOT NULL UNIQUE,          -- residential | office | social
    name        text NOT NULL,
    sort_order  int  NOT NULL DEFAULT 0
);

-- Группа классов внутри типа объекта (для офиса: "Офисные здания", "ТРЦ").
-- У жилых/соц групп нет — segment.group_id остаётся NULL.
CREATE TABLE segment_group (
    id               serial PRIMARY KEY,
    building_type_id int  NOT NULL REFERENCES building_type(id),
    name             text NOT NULL,
    sort_order       int  NOT NULL DEFAULT 0,
    UNIQUE (building_type_id, name),
    UNIQUE (id, building_type_id)              -- нужно для составного FK ниже
);

-- Класс/сегмент (колонка перечня). Набор задаётся данными на каждый тип.
CREATE TABLE segment (
    id               serial PRIMARY KEY,
    building_type_id int  NOT NULL REFERENCES building_type(id),
    group_id         int,
    name             text NOT NULL,
    sort_order       int  NOT NULL DEFAULT 0,
    UNIQUE (building_type_id, name),
    -- если группа задана, её тип объекта обязан совпадать с типом сегмента
    FOREIGN KEY (group_id, building_type_id)
        REFERENCES segment_group (id, building_type_id)
);

-- Дерево разделов — ОБЩЕЕ для всех типов объектов (ОВиК = ОВиК везде).
CREATE TABLE category (
    id          serial PRIMARY KEY,
    parent_id   int REFERENCES category(id),   -- NULL = верхний уровень
    name        text NOT NULL,
    sort_order  int  NOT NULL DEFAULT 0
);
CREATE INDEX ix_category_parent ON category(parent_id);

-- Позиция номенклатуры (строка перечня), привязана к листу дерева.
CREATE TABLE position (
    id           serial PRIMARY KEY,
    category_id  int  NOT NULL REFERENCES category(id),
    name         text NOT NULL,
    requirements text,                          -- тех. требования (то, что в скобках)
    source_ref   text,                          -- исходный № из файла (справочно; в файле — формула)
    sort_order   int  NOT NULL DEFAULT 0
);
CREATE INDEX ix_position_category ON position(category_id);

-- Справочник производителей (дедупликация).
CREATE TABLE vendor (
    id            serial PRIMARY KEY,
    name          text NOT NULL UNIQUE,         -- каноничное имя
    kind          vendor_kind NOT NULL DEFAULT 'manufacturer',
    represents_id int REFERENCES vendor(id),    -- бренд-владелец: "ИСТРАТЕХ (Grundfos)" -> Grundfos
    note          text
);

-- Синонимы и опечатки исходных файлов -> каноничный вендор.
-- (Durovit->Duravit, Cummnis->Cummins, "WILO (Native)" и т.п.)
CREATE TABLE vendor_alias (
    id        serial PRIMARY KEY,
    vendor_id int  NOT NULL REFERENCES vendor(id) ON DELETE CASCADE,
    alias     text NOT NULL UNIQUE
);

-- Реестр соглашений о сотрудничестве (звёздочка "*" в исходных файлах).
-- Один вендор может иметь историю соглашений (продления) — поэтому 1:N.
-- ЕДИНЫЙ критерий "звезды": существует соглашение со status='active'.
-- Даты (valid_until) — справочные; активность определяет ТОЛЬКО status.
CREATE TABLE agreement (
    id          serial PRIMARY KEY,
    vendor_id   int  NOT NULL REFERENCES vendor(id),
    status      agreement_status NOT NULL DEFAULT 'active',
    signed_on   date,
    valid_until date,
    doc_ref     text,
    note        text
);
CREATE INDEX ix_agreement_vendor ON agreement(vendor_id);
CREATE INDEX ix_agreement_active ON agreement(vendor_id) WHERE status = 'active';

-- Звезда вендора на ТЕКУЩИЙ момент (для живого перечня — деривируется, не хранится)
CREATE FUNCTION vendor_starred(p_vendor_id int) RETURNS boolean
  LANGUAGE sql STABLE AS
$$ SELECT EXISTS (SELECT 1 FROM agreement a
                  WHERE a.vendor_id = p_vendor_id AND a.status = 'active'); $$;

-- Аудит соглашений (append-only): "кто и когда поставил/снял звезду".
CREATE TABLE agreement_change_log (
    id           bigserial PRIMARY KEY,
    agreement_id int NOT NULL,
    action       change_action NOT NULL,
    old_value    jsonb,
    new_value    jsonb,
    changed_by   text        NOT NULL DEFAULT current_app_user(),
    changed_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agr_log_agreement ON agreement_change_log(agreement_id);
CREATE INDEX ix_agr_log_when      ON agreement_change_log(changed_at);

CREATE FUNCTION agreement_audit() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO agreement_change_log(agreement_id, action, new_value)
        VALUES (NEW.id, 'insert', to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO agreement_change_log(agreement_id, action, old_value, new_value)
        VALUES (NEW.id, 'update', to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO agreement_change_log(agreement_id, action, old_value)
        VALUES (OLD.id, 'delete', to_jsonb(OLD));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_agreement_audit
    AFTER INSERT OR UPDATE OR DELETE ON agreement
    FOR EACH ROW EXECUTE FUNCTION agreement_audit();


-- ===========================================================================
--  2. ЖИВОЕ СОСТОЯНИЕ + АУДИТ
-- ===========================================================================

-- Текущая правда: по строке на "позиция × класс × вендор".
-- Удаление — мягкое (deleted_at), чтобы аудит и снимки оставались целыми.
CREATE TABLE listing (
    id               serial PRIMARY KEY,
    position_id      int  NOT NULL REFERENCES position(id),
    segment_id       int  NOT NULL REFERENCES segment(id),
    vendor_id        int  REFERENCES vendor(id),        -- NULL для "-", пусто, требование
    status           listing_status NOT NULL DEFAULT 'allowed',
    spec_text        text,                              -- для requirement: "Россия", ГОСТ, "по согласованию"
    ujin_integration boolean NOT NULL DEFAULT false,    -- надстрочный "Ujin"
    note             text,                              -- область применения: "паркинг", "поквартирно"
    sort_order       int  NOT NULL DEFAULT 0,           -- порядок вендоров в ячейке (приоритет)

    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  text        NOT NULL DEFAULT current_app_user(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text        NOT NULL DEFAULT current_app_user(),
    deleted_at  timestamptz,
    deleted_by  text,

    CONSTRAINT listing_status_chk CHECK (
           (status = 'allowed'        AND vendor_id IS NOT NULL AND spec_text IS NULL)
        OR (status = 'requirement'    AND vendor_id IS NULL     AND spec_text IS NOT NULL)
        OR (status IN ('not_applicable','undefined') AND vendor_id IS NULL)
    )
);

-- один и тот же вендор не повторяется в одной живой ячейке
CREATE UNIQUE INDEX uq_listing_cell_vendor
    ON listing (position_id, segment_id, vendor_id)
    WHERE deleted_at IS NULL AND vendor_id IS NOT NULL;

-- не более одной мета-строки ("-", пусто, требование) на живую ячейку
CREATE UNIQUE INDEX uq_listing_cell_meta
    ON listing (position_id, segment_id)
    WHERE deleted_at IS NULL AND vendor_id IS NULL;

-- Ячейка — это ЛИБО список вендоров (allowed), ЛИБО одна мета-строка
-- (требование / "-" / пусто). Смешивание запрещено.
CREATE FUNCTION listing_cell_chk() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF NEW.deleted_at IS NOT NULL THEN
        RETURN NEW;                      -- удаляемая строка ячейку не ограничивает
    END IF;
    IF NEW.vendor_id IS NOT NULL THEN
        -- добавляем вендора: в ячейке не должно быть живой мета-строки
        IF EXISTS (SELECT 1 FROM listing l
                   WHERE l.position_id = NEW.position_id
                     AND l.segment_id  = NEW.segment_id
                     AND l.vendor_id IS NULL
                     AND l.deleted_at IS NULL
                     AND l.id <> NEW.id) THEN
            RAISE EXCEPTION
              'Ячейка (position %, segment %) уже содержит требование/прочерк — нельзя добавить вендора, сначала уберите мета-строку',
              NEW.position_id, NEW.segment_id;
        END IF;
    ELSE
        -- добавляем мета-строку: в ячейке не должно быть живых вендоров
        IF EXISTS (SELECT 1 FROM listing l
                   WHERE l.position_id = NEW.position_id
                     AND l.segment_id  = NEW.segment_id
                     AND l.vendor_id IS NOT NULL
                     AND l.deleted_at IS NULL
                     AND l.id <> NEW.id) THEN
            RAISE EXCEPTION
              'Ячейка (position %, segment %) уже содержит вендоров — нельзя добавить требование/прочерк, сначала уберите вендоров',
              NEW.position_id, NEW.segment_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_listing_cell_chk
    BEFORE INSERT OR UPDATE ON listing
    FOR EACH ROW EXECUTE FUNCTION listing_cell_chk();

CREATE INDEX ix_listing_position ON listing(position_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_listing_segment  ON listing(segment_id)  WHERE deleted_at IS NULL;
CREATE INDEX ix_listing_vendor   ON listing(vendor_id)   WHERE deleted_at IS NULL;

-- Журнал изменений (append-only). Полный аудит "кто/когда/что было->стало".
CREATE TABLE change_log (
    id          bigserial PRIMARY KEY,
    listing_id  int NOT NULL,
    action      change_action NOT NULL,
    old_value   jsonb,
    new_value   jsonb,
    changed_by  text        NOT NULL DEFAULT current_app_user(),
    changed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_change_log_listing ON change_log(listing_id);
CREATE INDEX ix_change_log_when    ON change_log(changed_at);

-- BEFORE: проставляем метки времени/авторов
CREATE FUNCTION listing_stamp() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.created_at := now();  NEW.created_by := current_app_user();
        NEW.updated_at := now();  NEW.updated_by := current_app_user();
    ELSIF TG_OP = 'UPDATE' THEN
        NEW.updated_at := now();  NEW.updated_by := current_app_user();
        IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
            NEW.deleted_by := current_app_user();
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_listing_stamp
    BEFORE INSERT OR UPDATE ON listing
    FOR EACH ROW EXECUTE FUNCTION listing_stamp();

-- AFTER: пишем в журнал
CREATE FUNCTION listing_audit() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO change_log(listing_id, action, new_value)
        VALUES (NEW.id, 'insert', to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO change_log(listing_id, action, old_value, new_value)
        VALUES (NEW.id, 'update', to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO change_log(listing_id, action, old_value)
        VALUES (OLD.id, 'delete', to_jsonb(OLD));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_listing_audit
    AFTER INSERT OR UPDATE OR DELETE ON listing
    FOR EACH ROW EXECUTE FUNCTION listing_audit();


-- ===========================================================================
--  3. ИЗДАНИЯ (РЕДАКЦИИ) + НЕИЗМЕНЯЕМЫЕ СНИМКИ
-- ===========================================================================

CREATE TABLE release (
    id               serial PRIMARY KEY,
    building_type_id int  NOT NULL REFERENCES building_type(id),
    label            text NOT NULL,            -- "к Стандартам, 25.03.2026"
    effective_date   date,
    status           release_status NOT NULL DEFAULT 'open',
    author           text,
    frozen_at        timestamptz,              -- момент фиксации снимка
    created_at       timestamptz NOT NULL DEFAULT now()
);
-- не более одной открытой (редактируемой) редакции на тип объекта
CREATE UNIQUE INDEX uq_release_one_open
    ON release (building_type_id) WHERE status = 'open';

-- Снимок издания. Имена денормализованы НАМЕРЕННО: даже если позицию или
-- вендора потом переименуют, выгрузка по этой редакции воспроизведётся 1-в-1.
CREATE TABLE release_listing (
    id                  bigserial PRIMARY KEY,
    release_id          int NOT NULL REFERENCES release(id) ON DELETE CASCADE,
    position_id         int,
    segment_id          int,
    vendor_id           int,
    status              listing_status NOT NULL,
    spec_text           text,
    ujin_integration    boolean NOT NULL DEFAULT false,
    note                text,
    sort_order          int NOT NULL DEFAULT 0,
    -- денормализованные подписи на момент фиксации
    category_path       text,
    position_name       text,
    segment_group_name  text,
    segment_name        text,
    vendor_name         text,
    vendor_starred      boolean NOT NULL DEFAULT false  -- "*" на момент фиксации
);
CREATE INDEX ix_release_listing_release ON release_listing(release_id);

-- Путь раздела "Оборудование / Инженерное оборудование / ОВиК"
CREATE FUNCTION category_path(p_id int) RETURNS text
  LANGUAGE sql STABLE AS
$$
    WITH RECURSIVE up AS (
        SELECT id, parent_id, name, 1 AS lvl FROM category WHERE id = p_id
        UNION ALL
        SELECT c.id, c.parent_id, c.name, up.lvl + 1
        FROM category c JOIN up ON c.id = up.parent_id
    )
    SELECT string_agg(name, ' / ' ORDER BY lvl DESC) FROM up;
$$;

-- Фиксация редакции: копируем текущее живое состояние в снимок и публикуем.
CREATE FUNCTION freeze_release(p_release_id int, p_author text DEFAULT NULL)
  RETURNS void LANGUAGE plpgsql AS
$$
DECLARE
    v_bt int;
    v_st release_status;
BEGIN
    SELECT building_type_id, status INTO v_bt, v_st
    FROM release WHERE id = p_release_id FOR UPDATE;

    IF v_bt IS NULL THEN
        RAISE EXCEPTION 'Релиз % не найден', p_release_id;
    END IF;
    IF v_st <> 'open' THEN
        RAISE EXCEPTION 'Релиз % уже зафиксирован (статус %)', p_release_id, v_st;
    END IF;

    INSERT INTO release_listing (
        release_id, position_id, segment_id, vendor_id, status, spec_text,
        ujin_integration, note, sort_order,
        category_path, position_name, segment_group_name, segment_name, vendor_name,
        vendor_starred)
    SELECT p_release_id, l.position_id, l.segment_id, l.vendor_id, l.status, l.spec_text,
           l.ujin_integration, l.note, l.sort_order,
           category_path(pos.category_id), pos.name, sg.name, seg.name, v.name,
           -- "*" фиксируется НА МОМЕНТ издания: истечение соглашения потом
           -- не изменит уже опубликованную редакцию
           coalesce(vendor_starred(l.vendor_id), false)
    FROM listing l
    JOIN segment  seg ON seg.id = l.segment_id
    LEFT JOIN segment_group sg ON sg.id = seg.group_id
    JOIN position pos ON pos.id = l.position_id
    LEFT JOIN vendor v ON v.id = l.vendor_id
    WHERE seg.building_type_id = v_bt
      AND l.deleted_at IS NULL;

    UPDATE release
       SET status = 'published',
           frozen_at = now(),
           author = coalesce(p_author, author)
     WHERE id = p_release_id;
END;
$$;


-- Живой перечень для отображения: только живые строки, звезда "*" вычисляется
-- по текущим соглашениям (никогда не хранится в listing).
CREATE VIEW listing_live AS
SELECT
    l.id, l.position_id, l.segment_id, l.vendor_id,
    l.status, l.spec_text, l.ujin_integration, l.note, l.sort_order,
    category_path(pos.category_id)          AS category_path,
    pos.name                                AS position_name,
    sg.name                                 AS segment_group_name,
    seg.name                                AS segment_name,
    v.name                                  AS vendor_name,
    CASE WHEN l.vendor_id IS NOT NULL
         THEN vendor_starred(l.vendor_id)
         ELSE false END                     AS vendor_starred,
    l.updated_at, l.updated_by
FROM listing l
JOIN segment  seg ON seg.id = l.segment_id
LEFT JOIN segment_group sg ON sg.id = seg.group_id
JOIN position pos ON pos.id = l.position_id
LEFT JOIN vendor v ON v.id = l.vendor_id
WHERE l.deleted_at IS NULL;


-- ===========================================================================
--  СИДЫ: типы объектов и наборы классов трёх известных перечней
-- ===========================================================================

INSERT INTO building_type (code, name, sort_order) VALUES
    ('residential', 'Жилые здания',           1),
    ('office',      'Офисные здания / ТРЦ',    2),
    ('social',      'Социальные объекты',      3);

-- Жилые: 6 классов, без групп
INSERT INTO segment (building_type_id, name, sort_order)
SELECT bt.id, x.name, x.ord
FROM building_type bt,
     (VALUES ('Делюкс (Элит)',1),('Премиум',2),('Бизнес-Премиум',3),
             ('Бизнес',4),('Комфорт',5),('Эконом',6)) AS x(name, ord)
WHERE bt.code = 'residential';

-- Офисные: две группы — "Офисные здания" {Prime, Класс А, Класс B} и "ТРЦ" {ТРЦ}
INSERT INTO segment_group (building_type_id, name, sort_order)
SELECT id, 'Офисные здания', 1 FROM building_type WHERE code = 'office';
INSERT INTO segment_group (building_type_id, name, sort_order)
SELECT id, 'ТРЦ', 2 FROM building_type WHERE code = 'office';

INSERT INTO segment (building_type_id, group_id, name, sort_order)
SELECT bt.id, g.id, x.name, x.ord
FROM building_type bt
JOIN segment_group g ON g.building_type_id = bt.id AND g.name = 'Офисные здания',
     (VALUES ('Prime',1),('Класс А',2),('Класс B',3)) AS x(name, ord)
WHERE bt.code = 'office';

INSERT INTO segment (building_type_id, group_id, name, sort_order)
SELECT bt.id, g.id, 'ТРЦ', 1
FROM building_type bt
JOIN segment_group g ON g.building_type_id = bt.id AND g.name = 'ТРЦ'
WHERE bt.code = 'office';

-- Социальные: один класс, без групп
INSERT INTO segment (building_type_id, name, sort_order)
SELECT id, 'Социальные объекты', 1 FROM building_type WHERE code = 'social';

COMMIT;
