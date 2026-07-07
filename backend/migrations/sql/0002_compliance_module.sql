-- ============================================================================
--  Модуль соответствия проектов стандартам — схема compliance, PostgreSQL
--  Надстройка над ядром вендор-листа (public.*). Ядро не меняется
--  (единственные добавления к ядру — два аддитивных индекса, помечены ниже).
--
--  Назначение:
--    Свести в одно место выбор оборудования по проектам (сегодня разбросан
--    по PDF/DWG разных проектировщиков) и подсветить отступления от стандарта.
--
--  Инварианты:
--    * Стандарты внепроектны; проект пинится к ОДНОМУ классу (segment).
--    * На позицию можно выбрать НЕСКОЛЬКО вендоров; можно ЛЮБОГО из справочника
--      (в т.ч. вне стандарта) — чтобы занести реальность и увидеть отступления.
--    * Соответствие НЕ хранится, а ВЫЧИСЛЯЕТСЯ против ЖИВОГО listing.
--
--  СВЕТОФОР ПО ПОЗИЦИИ (position_state) — итог согласованных решений:
--    🟢 compliant    — в стандарте есть список разрешённых для класса проекта,
--                      выбор сделан, и ВСЕ выбранные вендоры из списка
--                      (строго: ни одного лишнего). Судит машина.
--    🔴 deviation    — список разрешённых есть, выбор сделан, но хотя бы один
--                      вендор вне списка. Судит машина.
--    🟡 manual_check — списка нет: только условие ("Россия"/"ГОСТ"/
--                      "по согласованию") или прочерк "–". Машина не судит,
--                      помечает на ручную проверку (см. standard_requirement).
--    ⚪ open         — позиция в области стандарта, но выбор ещё не сделан.
--
--    Процент соответствия = 🟢 / (🟢 + 🔴). Жёлтые и открытые в процент
--    НЕ подмешиваются (иначе цифра врёт), показываются отдельными числами.
--
--  Решения редакции:
--    1. Бренды-представители: соответствие по "бренд-ключу"
--       coalesce(represents_id, id) — представитель разрешённого бренда
--       (и наоборот) засчитывается как соответствие.
--    2. Любое требование/прочерк = 🟡: данных для авто-проверки нет
--       (в справочнике вендоров нет страны/признака ГОСТ).
--    3. Универсум позиций = стандарт ∪ выбор проекта, поэтому отступления
--       и выборы на непрофильных позициях не теряются.
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS compliance;

-- Аддитивные индексы на ядро под подзапросы отчётных вьюх. Поведение не меняют.
CREATE INDEX IF NOT EXISTS ix_listing_std_lookup
    ON public.listing (segment_id, position_id, vendor_id)
    WHERE status = 'allowed' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_listing_req_lookup
    ON public.listing (segment_id, position_id)
    WHERE status = 'requirement' AND deleted_at IS NULL;

-- Бренд-ключ вендора: сам бренд, либо тот, кого он представляет.
-- ИСТРАТЕХ (represents -> Grundfos) и Grundfos дают один и тот же ключ.
CREATE OR REPLACE FUNCTION compliance.brand_key(p_vendor_id int) RETURNS int
    LANGUAGE sql STABLE AS
$$ SELECT coalesce(represents_id, id) FROM public.vendor WHERE id = p_vendor_id; $$;


-- ===========================================================================
--  ПРОЕКТ — привязан к одному классу (segment)
-- ===========================================================================
CREATE TABLE compliance.project (
    id          serial PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    segment_id  int  NOT NULL REFERENCES public.segment(id),
    release_id  int  REFERENCES public.release(id),   -- справочно; на флаг не влияет
    note        text,

    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  text        NOT NULL DEFAULT public.current_app_user(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text        NOT NULL DEFAULT public.current_app_user()
);
CREATE INDEX ix_project_segment ON compliance.project(segment_id);
CREATE INDEX ix_project_release ON compliance.project(release_id);

CREATE FUNCTION compliance.project_stamp() RETURNS trigger LANGUAGE plpgsql AS
$$
DECLARE
    v_rel_bt int;
    v_seg_bt int;
BEGIN
    IF NEW.release_id IS NOT NULL THEN
        SELECT building_type_id INTO v_rel_bt FROM public.release  WHERE id = NEW.release_id;
        SELECT building_type_id INTO v_seg_bt FROM public.segment  WHERE id = NEW.segment_id;
        IF v_rel_bt IS DISTINCT FROM v_seg_bt THEN
            RAISE EXCEPTION
              'Класс (segment %) и указанное издание (release %) — разные типы объектов',
              NEW.segment_id, NEW.release_id;
        END IF;
    END IF;

    IF TG_OP = 'INSERT' THEN
        NEW.created_at := now();  NEW.created_by := public.current_app_user();
    END IF;
    NEW.updated_at := now();  NEW.updated_by := public.current_app_user();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_project_stamp
    BEFORE INSERT OR UPDATE ON compliance.project
    FOR EACH ROW EXECUTE FUNCTION compliance.project_stamp();


-- ===========================================================================
--  ВЫБОР ВЕНДОРА — N на позицию, любой вендор; мягкое удаление + аудит
-- ===========================================================================
CREATE TABLE compliance.project_selection (
    id          serial PRIMARY KEY,
    project_id  int NOT NULL REFERENCES compliance.project(id) ON DELETE CASCADE,
    position_id int NOT NULL REFERENCES public.position(id),
    vendor_id   int NOT NULL REFERENCES public.vendor(id),
    rationale   text,        -- основание для отступления / ссылка на согласование
    source_ref  text,        -- откуда взято: лист DWG, раздел PDF и т.п.

    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  text        NOT NULL DEFAULT public.current_app_user(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text        NOT NULL DEFAULT public.current_app_user(),
    deleted_at  timestamptz,
    deleted_by  text
);
-- один вендор на позицию не дублируется среди живых строк
CREATE UNIQUE INDEX uq_psel_active
    ON compliance.project_selection (project_id, position_id, vendor_id)
    WHERE deleted_at IS NULL;
CREATE INDEX ix_psel_project  ON compliance.project_selection(project_id)  WHERE deleted_at IS NULL;
CREATE INDEX ix_psel_position ON compliance.project_selection(position_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_psel_vendor   ON compliance.project_selection(vendor_id)   WHERE deleted_at IS NULL;

-- Журнал изменений выбора (append-only) — переиспользуем enum ядра.
CREATE TABLE compliance.selection_change_log (
    id            bigserial PRIMARY KEY,
    selection_id  int NOT NULL,
    action        public.change_action NOT NULL,
    old_value     jsonb,
    new_value     jsonb,
    changed_by    text        NOT NULL DEFAULT public.current_app_user(),
    changed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_sel_log_selection ON compliance.selection_change_log(selection_id);
CREATE INDEX ix_sel_log_when      ON compliance.selection_change_log(changed_at);

CREATE FUNCTION compliance.selection_stamp() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.created_at := now();  NEW.created_by := public.current_app_user();
        NEW.updated_at := now();  NEW.updated_by := public.current_app_user();
    ELSIF TG_OP = 'UPDATE' THEN
        NEW.updated_at := now();  NEW.updated_by := public.current_app_user();
        IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
            NEW.deleted_by := public.current_app_user();      -- проставить автора удаления
        ELSIF NEW.deleted_at IS NULL AND OLD.deleted_at IS NOT NULL THEN
            NEW.deleted_by := NULL;                           -- очистить при восстановлении
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_selection_stamp
    BEFORE INSERT OR UPDATE ON compliance.project_selection
    FOR EACH ROW EXECUTE FUNCTION compliance.selection_stamp();

CREATE FUNCTION compliance.selection_audit() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO compliance.selection_change_log(selection_id, action, new_value)
        VALUES (NEW.id, 'insert', to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO compliance.selection_change_log(selection_id, action, old_value, new_value)
        VALUES (NEW.id, 'update', to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO compliance.selection_change_log(selection_id, action, old_value)
        VALUES (OLD.id, 'delete', to_jsonb(OLD));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_selection_audit
    AFTER INSERT OR UPDATE OR DELETE ON compliance.project_selection
    FOR EACH ROW EXECUTE FUNCTION compliance.selection_audit();


-- ===========================================================================
--  ОТЧЁТНЫЕ ПРЕДСТАВЛЕНИЯ
-- ===========================================================================

-- Гранулярно: каждый живой выбор + признак соответствия (по бренд-ключу)
-- и текст требования стандарта на этой позиции, если он есть.
CREATE VIEW compliance.project_selection_detail AS
SELECT
    ps.id,
    ps.project_id,
    p.code            AS project_code,
    p.name            AS project_name,
    public.category_path(pos.category_id) AS category_path,
    pos.name          AS position_name,
    seg.name          AS segment_name,
    v.name            AS vendor_name,
    ps.position_id,
    ps.vendor_id,
    ps.rationale,
    ps.source_ref,
    ps.created_at,
    ps.created_by,
    EXISTS (
        SELECT 1 FROM public.listing l
        WHERE l.segment_id  = p.segment_id
          AND l.position_id = ps.position_id
          AND l.status = 'allowed'
          AND l.deleted_at IS NULL
          AND compliance.brand_key(l.vendor_id) = compliance.brand_key(ps.vendor_id)
    ) AS in_standard,
    (
        SELECT string_agg(DISTINCT l2.spec_text, '; ')
        FROM public.listing l2
        WHERE l2.segment_id  = p.segment_id
          AND l2.position_id = ps.position_id
          AND l2.status = 'requirement'
          AND l2.deleted_at IS NULL
    ) AS standard_requirement
FROM compliance.project_selection ps
JOIN compliance.project p   ON p.id   = ps.project_id
JOIN public.segment seg     ON seg.id = p.segment_id
JOIN public.position pos    ON pos.id = ps.position_id
JOIN public.vendor v        ON v.id   = ps.vendor_id
WHERE ps.deleted_at IS NULL;

-- Светофор по позициям. Универсум = позиции стандарта (для класса проекта)
-- ОБЪЕДИНЁННЫЕ с позициями, по которым в проекте есть выбор.
CREATE VIEW compliance.project_position_status AS
SELECT
    q.*,
    (q.selected_vendor_count - q.off_standard_count) AS in_standard_selected_count,
    (q.selected_vendor_count > 0)                    AS has_selection,
    (q.allowed_vendor_count  > 0)                    AS in_standard_scope,
    CASE
        WHEN q.allowed_vendor_count  = 0 THEN 'manual_check'  -- 🟡 списка нет: требование/«–»
        WHEN q.selected_vendor_count = 0 THEN 'open'          -- ⚪ есть список, выбора нет
        WHEN q.off_standard_count    > 0 THEN 'deviation'     -- 🔴 есть лишний (строго)
        ELSE                                  'compliant'     -- 🟢 всё из списка
    END AS position_state
FROM (
    WITH universe AS (
        SELECT p.id AS project_id, l.position_id
        FROM compliance.project p
        JOIN public.listing l
          ON l.segment_id = p.segment_id
         AND l.status = 'allowed'
         AND l.deleted_at IS NULL
        UNION
        SELECT ps.project_id, ps.position_id
        FROM compliance.project_selection ps
        WHERE ps.deleted_at IS NULL
    )
    SELECT
        p.id   AS project_id,
        p.code AS project_code,
        u.position_id,
        public.category_path(pos.category_id) AS category_path,
        pos.name                              AS position_name,
        (
            SELECT count(DISTINCT l.vendor_id) FROM public.listing l
            WHERE l.segment_id = p.segment_id AND l.position_id = u.position_id
              AND l.status = 'allowed' AND l.deleted_at IS NULL
        ) AS allowed_vendor_count,
        (
            SELECT count(DISTINCT ps.vendor_id) FROM compliance.project_selection ps
            WHERE ps.project_id = p.id AND ps.position_id = u.position_id
              AND ps.deleted_at IS NULL
        ) AS selected_vendor_count,
        (
            SELECT count(DISTINCT ps.vendor_id) FROM compliance.project_selection ps
            WHERE ps.project_id = p.id AND ps.position_id = u.position_id
              AND ps.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM public.listing l
                  WHERE l.segment_id = p.segment_id AND l.position_id = u.position_id
                    AND l.status = 'allowed' AND l.deleted_at IS NULL
                    AND compliance.brand_key(l.vendor_id) = compliance.brand_key(ps.vendor_id)
              )
        ) AS off_standard_count,
        (
            SELECT string_agg(DISTINCT l.spec_text, '; ') FROM public.listing l
            WHERE l.segment_id = p.segment_id AND l.position_id = u.position_id
              AND l.status = 'requirement' AND l.deleted_at IS NULL
        ) AS standard_requirement
    FROM universe u
    JOIN compliance.project p ON p.id  = u.project_id
    JOIN public.position pos  ON pos.id = u.position_id
) q;

-- Сводка по проекту — честный процент + раскладка по светофору.
CREATE VIEW compliance.project_summary AS
SELECT
    project_id,
    project_code,
    count(*)                                                   AS total_positions,
    count(*) FILTER (WHERE position_state = 'compliant')       AS compliant_positions,   -- 🟢
    count(*) FILTER (WHERE position_state = 'deviation')       AS deviation_positions,   -- 🔴
    count(*) FILTER (WHERE position_state = 'manual_check')    AS manual_check_positions,-- 🟡
    count(*) FILTER (WHERE position_state = 'open')            AS open_positions,        -- ⚪
    count(*) FILTER (WHERE position_state IN ('compliant','deviation')) AS judged_positions,
    coalesce(sum(off_standard_count) FILTER (WHERE in_standard_scope), 0)
                                                               AS off_standard_selections,
    round(
        100.0 * count(*) FILTER (WHERE position_state = 'compliant')
        / nullif(count(*) FILTER (WHERE position_state IN ('compliant','deviation')), 0)
    , 1) AS compliance_pct      -- 🟢 / (🟢 + 🔴); NULL, если судить ещё нечего
FROM compliance.project_position_status
GROUP BY project_id, project_code;

COMMIT;
