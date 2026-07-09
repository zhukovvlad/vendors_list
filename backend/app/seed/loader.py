"""Сборка плана загрузки (DB-free) и его исполнение (async SQLAlchemy Core).

build_load: reader + parse + дерево → LoadPlan (для dry-run и реального прогона).
execute/run — Task 8 (дописываются ниже).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import get_engine

from .parse import CategoryNode, CategoryTree, RowKind, SeedError, classify_cell
from .reader import ClassColumn, ReadRow, SheetData, read_workbook
from .report import FileReport, RunReport

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class PositionRow:
    pos_key: int
    category_number: tuple[int, ...]
    name: str
    source_ref: str | None
    sort_order: int


@dataclass(frozen=True)
class ListingRow:
    pos_key: int
    building_type: str
    segment_name: str
    status: str
    vendor_name: str | None
    ujin: bool
    spec_text: str | None
    note: str | None
    sort_order: int


@dataclass
class LoadPlan:
    categories: list[CategoryNode]
    positions: list[PositionRow]
    listings: list[ListingRow]
    vendors: dict[str, bool]
    effective_date: dict[str, str | None]
    report: RunReport


def _column_map(classes: list[ClassColumn]) -> dict[int, ClassColumn]:
    return {c.col: c for c in classes}


def build_load(paths: list[str]) -> LoadPlan:
    tree = CategoryTree()
    positions: list[PositionRow] = []
    listings: list[ListingRow] = []
    vendors: dict[str, bool] = {}
    effective_date: dict[str, str | None] = {}
    file_reports: list[FileReport] = []
    pos_counter = 0

    for path in paths:
        data: SheetData = read_workbook(path)
        m = _DATE_RE.search(path)
        effective_date[data.building_type] = m.group(1) if m else None
        cols = _column_map(data.classes)
        fr = FileReport(data.building_type, data.sheet_title, data.hidden_sheets)
        fr.listings_by_status = {"allowed": 0, "not_applicable": 0, "requirement": 0}
        current: tuple[int, ...] | None = None

        for rr in data.rows:
            kind = rr.row.kind
            if kind is RowKind.BLANK:
                fr.blanks += 1
                continue
            if kind is RowKind.FOOTNOTE:
                fr.footnotes += 1
                continue
            if kind is RowKind.HEADING:
                assert rr.row.number is not None and rr.row.name is not None
                tree.add(rr.row.number, rr.row.name, file_label=data.building_type)
                current = rr.row.number
                fr.headings += 1
                continue
            # POSITION
            if current is None:
                raise _pos_without_heading(path, rr)
            assert rr.row.name is not None
            pos_counter += 1
            pos_key = pos_counter
            positions.append(
                PositionRow(pos_key, current, rr.row.name, rr.row.source_ref, fr.positions)
            )
            fr.positions += 1
            for col, cell_text in rr.cells.items():
                seg = cols[col].segment_name
                # Дедуп вендора В ПРЕДЕЛАХ ЯЧЕЙКИ: uq_listing_cell_vendor запрещает
                # один vendor_id дважды в живой (position, segment). Два токена с
                # одинаковым итоговым именем (напр. 'System Air*, System Air') иначе
                # уронили бы реальный INSERT на уникальном индексе. Дубль пропускаем
                # + предупреждение с локацией; звезду вендора при этом НЕ теряем
                # (агрегируется в vendors до skip).
                seen_vendors: set[str] = set()
                for cl in classify_cell(cell_text):
                    if cl.status == "allowed":
                        assert cl.vendor_name is not None
                        vendors[cl.vendor_name] = vendors.get(cl.vendor_name, False) or cl.starred
                        if cl.vendor_name in seen_vendors:
                            fr.warnings.append(
                                f"строка {rr.row_no}, класс {seg!r}: повтор вендора "
                                f"{cl.vendor_name!r} в ячейке — дубль пропущен "
                                f"(uq_listing_cell_vendor)"
                            )
                            continue
                        seen_vendors.add(cl.vendor_name)
                        fr.vendor_tokens += 1
                        if "Требование:" in (cl.note or ""):
                            fr.warnings.append(f"строка {rr.row_no}: смешанная ячейка → {cl.note}")
                    elif cl.status == "not_applicable":
                        fr.dash_cells += 1
                    else:  # requirement
                        fr.requirement_cells += 1
                    fr.listings_by_status[cl.status] = fr.listings_by_status.get(cl.status, 0) + 1
                    listings.append(
                        ListingRow(
                            pos_key, data.building_type, seg, cl.status,
                            cl.vendor_name, cl.ujin, cl.spec_text, cl.note, cl.sort_order,
                        )
                    )
        file_reports.append(fr)

    tree.integrity_check()
    star_occ = sum(
        1 for ln in listings
        if ln.status == "allowed" and vendors.get(ln.vendor_name or "", False)
    )
    report = RunReport(
        files=file_reports,
        vendors_unique=len(vendors),
        agreements=sum(1 for v in vendors.values() if v),
        star_occurrences=star_occ,
        categories=len(tree.ordered()),
        category_warnings=tree.warnings,
    )
    return LoadPlan(tree.ordered(), positions, listings, vendors, effective_date, report)


def _pos_without_heading(path: str, rr: ReadRow) -> SeedError:
    return SeedError(f"{path} строка {rr.row_no}: позиция вне раздела (нет текущего заголовка)")


# Порядок УДАЛЕНИЯ (дети → родители). DELETE, НЕ TRUNCATE CASCADE — чтобы
# гарантированно не задеть compliance.project* (§14, требование ревьюера).
# Аудируемую таблицу удаляем ПЕРЕД её журналом (listing→change_log,
# agreement→agreement_change_log): DELETE аудируемой таблицы срабатывает AFTER-DELETE-
# триггером и пишет 'delete'-строки в журнал, которые затем стирает DELETE журнала.
# Иначе журнал очищается раньше, а последующий DELETE родителя плодит осиротевшие
# строки (у agreement_change_log нет FK на agreement) — накапливались бы на ре-сид.
_RESET_ORDER = (
    "release_listing", "release", "listing", "change_log",
    "agreement", "agreement_change_log",
    "position", "vendor_alias", "vendor", "category",
)


async def _guard_no_projects(conn: AsyncConnection, force: bool) -> None:
    row = await conn.execute(
        text(
            "SELECT (SELECT count(*) FROM compliance.project) "
            "     + (SELECT count(*) FROM compliance.project_selection) AS n"
        )
    )
    n = int(row.scalar_one())
    if n > 0 and not force:
        raise SeedError(
            f"Стандарты уже используются проектами ({n} строк в compliance). "
            "Правки — в приложении. Перезапись только с --force (проектные данные не трогаются)."
        )


async def _apply_timeouts(conn: AsyncConnection) -> None:
    # Операционная страховка сессии сида (SET LOCAL — живёт только в этой транзакции).
    # ВНИМАНИЕ (инвариант): idle=15s безопасен ТОЛЬКО потому, что build_load
    # (весь парсинг Excel) в run() исполняется ДО begin() — внутри транзакции
    # клиентских пауз нет, лишь пайплайн вставок с мс-зазорами. Перенос парсинга
    # внутрь транзакции сделает 15s миной. statement_timeout де-факто сторожит
    # _reset (каскад DELETE) и freeze_release; для executemany в extended-протоколе
    # таймер гасится завершением каждого Execute (запас огромен). Значения —
    # литеральные константы (не пользовательский ввод), инъекции нет.
    await conn.execute(text("SET LOCAL statement_timeout = '60s'"))
    await conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = '15s'"))


async def _reset(conn: AsyncConnection) -> None:
    for tbl in _RESET_ORDER:
        await conn.execute(text(f"DELETE FROM public.{tbl}"))  # compliance НЕ трогаем


async def _prealloc_ids(conn: AsyncConnection, table: str, n: int) -> list[int]:
    # Предвыделяем n id из sequence таблицы — вместо RETURNING (порядок строк в
    # INSERT ... RETURNING формально не документирован). Порядок возврата неважен:
    # нужны просто n уникальных значений. nextval НЕТРАНЗАКЦИОНЕН — при откате
    # значения «сгорают», дырки в id легальны. setval НЕ нужен: id взяты из этого
    # же sequence, поэтому он уже «впереди».
    if n == 0:
        return []
    rows = await conn.execute(
        text("SELECT nextval(pg_get_serial_sequence(:t, 'id')) "
             "FROM generate_series(1, :n)"),
        {"t": table, "n": n},
    )
    return [int(x) for x in rows.scalars().all()]


async def execute(
    conn: AsyncConnection, plan: LoadPlan, *, author: str, freeze: bool, force: bool
) -> None:
    # 1. Идентичность аудита (SET LOCAL-семантика; логин bind-параметром)
    await conn.execute(text("SELECT set_config('app.user', :u, true)"), {"u": author})
    # 2. Защита + сброс
    await _guard_no_projects(conn, force)
    await _reset(conn)

    # 3. Предвыделение id для таблиц, чьи id нужны downstream (документированно,
    #    без RETURNING). Порядок возврата неважен — раскладываем позиционно.
    vendor_names = list(plan.vendors)
    cat_ids = await _prealloc_ids(conn, "category", len(plan.categories))
    pos_ids = await _prealloc_ids(conn, "position", len(plan.positions))
    ven_ids = await _prealloc_ids(conn, "vendor", len(vendor_names))
    cat_id: dict[tuple[int, ...], int] = {
        node.number: cid for node, cid in zip(plan.categories, cat_ids, strict=True)
    }
    pos_id: dict[int, int] = {
        pos.pos_key: pid for pos, pid in zip(plan.positions, pos_ids, strict=True)
    }
    vendor_id: dict[str, int] = {
        name: vid for name, vid in zip(vendor_names, ven_ids, strict=True)
    }

    # 4. Категории — один executemany с явным id + parent_id из карты.
    #    ВНИМАНИЕ: список параметров ОБЯЗАН идти родители-раньше-детей
    #    (plan.categories == tree.ordered()). asyncpg executemany выполняет наборы
    #    строго последовательно в порядке списка — это (а не DEFERRABLE) держит FK
    #    parent_id валидным построчно. НЕ переводить на multi-row VALUES / чанки /
    #    параллельные вставки — тихо сломается валидность родителей.
    if plan.categories:
        await conn.execute(
            text("INSERT INTO category(id, parent_id, name, sort_order) "
                 "VALUES (:id, :p, :n, :s)"),
            [{"id": cat_id[node.number],
              "p": cat_id[node.parent] if node.parent is not None else None,
              "n": node.name, "s": node.sort_order}
             for node in plan.categories],
        )

    # 5. Позиции — один executemany с явным id + category_id из карты.
    if plan.positions:
        await conn.execute(
            text("INSERT INTO position(id, category_id, name, source_ref, sort_order) "
                 "VALUES (:id, :c, :n, :sr, :s)"),
            [{"id": pos_id[pos.pos_key], "c": cat_id[pos.category_number],
              "n": pos.name, "sr": pos.source_ref, "s": pos.sort_order}
             for pos in plan.positions],
        )

    # 6. Вендоры — один executemany с явным id. Соглашения (звезда) — отдельный
    #    executemany по звёздным вендорам (свой id agreement downstream не нужен —
    #    остаётся на default sequence). agreement-change_log триггер сработает
    #    построчно и возьмёт автора из app.user (см. п.1).
    if vendor_names:
        await conn.execute(
            text("INSERT INTO vendor(id, name) VALUES (:id, :n)"),
            [{"id": vendor_id[name], "n": name} for name in vendor_names],
        )
    starred = [name for name, is_starred in plan.vendors.items() if is_starred]
    if starred:
        await conn.execute(
            text("INSERT INTO agreement(vendor_id, status) VALUES (:v, 'active')"),
            [{"v": vendor_id[name]} for name in starred],
        )

    # 7. Карта сегментов (code, segment_name) -> id (справочник уже засеян 0001)
    seg_rows = await conn.execute(
        text("SELECT s.id, s.name, bt.code FROM public.segment s "
             "JOIN public.building_type bt ON bt.id = s.building_type_id")
    )
    seg_id: dict[tuple[str, str], int] = {(r.code, r.name): r.id for r in seg_rows}

    # 8. Листинги (триггеры проставят автора/аудит/инвариант ячейки)
    for ln in plan.listings:
        key = (ln.building_type, ln.segment_name)
        if key not in seg_id:
            avail = sorted(n for (c, n) in seg_id if c == ln.building_type)
            raise SeedError(
                f"Класс {ln.segment_name!r} ({ln.building_type}) не найден в segment. "
                f"Доступны: {avail}"
            )
        await conn.execute(
            text("INSERT INTO listing(position_id, segment_id, vendor_id, status, "
                 "spec_text, ujin_integration, note, sort_order) "
                 "VALUES (:p, :seg, :v, :st, :spec, :ujin, :note, :so)"),
            {"p": pos_id[ln.pos_key], "seg": seg_id[key],
             "v": vendor_id[ln.vendor_name] if ln.vendor_name else None,
             "st": ln.status, "spec": ln.spec_text, "ujin": ln.ujin,
             "note": ln.note, "so": ln.sort_order},
        )

    # 9. Опциональная фиксация первого издания (по умолчанию выкл, §13)
    if freeze:
        bt_rows = await conn.execute(text("SELECT id, code FROM public.building_type"))
        bt_id = {r.code: r.id for r in bt_rows}
        present = {ln.building_type for ln in plan.listings}
        for code in present:
            eff = plan.effective_date.get(code)
            label = f"к Стандартам, {eff}" if eff else "к Стандартам (сид)"
            # asyncpg — строгий драйвер: date-колонка требует datetime.date,
            # implicit str->date (как у psycopg2) он не делает.
            eff_date = date.fromisoformat(eff) if eff else None
            rel = await conn.execute(
                text("INSERT INTO release(building_type_id, label, effective_date, status) "
                     "VALUES (:bt, :l, :d, 'open') RETURNING id"),
                {"bt": bt_id[code], "l": label, "d": eff_date},
            )
            await conn.execute(
                text("SELECT freeze_release(:rid, :a)"),
                {"rid": int(rel.scalar_one()), "a": author},
            )


async def run(
    paths: list[str], *, dry_run: bool, author: str, freeze: bool, force: bool, verify: bool
) -> int:
    plan = build_load(paths)  # DB-free
    print(plan.report.render())
    if verify:
        mismatches = plan.report.verify()
        if mismatches:
            print("\n❌ Калибровка не сошлась:")
            for m in mismatches:
                print(f"  - {m}")
            return 1
        print("\n✅ Калибровка сошлась (заголовки/позиции/сноски).")
    if dry_run:
        print("\n(dry-run: БД не изменялась)")
        return 0
    async with get_engine().begin() as conn:
        await _apply_timeouts(conn)
        await execute(conn, plan, author=author, freeze=freeze, force=force)
    print("\n✅ Записано в БД.")
    return 0
