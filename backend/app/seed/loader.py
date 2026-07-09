"""Сборка плана загрузки (DB-free) и его исполнение (async SQLAlchemy Core).

build_load: reader + parse + дерево → LoadPlan (для dry-run и реального прогона).
execute/run — Task 8 (дописываются ниже).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import CategoryNode, CategoryTree, RowKind, classify_cell
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
                PositionRow(pos_key, current, rr.row.name, rr.row.source_ref, len(positions))
            )
            fr.positions += 1
            for col, text in rr.cells.items():
                seg = cols[col].segment_name
                # Дедуп вендора В ПРЕДЕЛАХ ЯЧЕЙКИ: uq_listing_cell_vendor запрещает
                # один vendor_id дважды в живой (position, segment). Два токена с
                # одинаковым итоговым именем (напр. 'System Air*, System Air') иначе
                # уронили бы реальный INSERT на уникальном индексе. Дубль пропускаем
                # + предупреждение с локацией; звезду вендора при этом НЕ теряем
                # (агрегируется в vendors до skip).
                seen_vendors: set[str] = set()
                for cl in classify_cell(text):
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


def _pos_without_heading(path: str, rr: ReadRow) -> Exception:  # noqa: ANN202 — вспомогательный
    from .parse import SeedError

    return SeedError(f"{path} строка {rr.row_no}: позиция вне раздела (нет текущего заголовка)")
