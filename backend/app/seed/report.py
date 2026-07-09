"""Аккумулятор счётчиков прогона + рендер отчёта + сверка с калибровкой (§19)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Жёсткие поля калибровки (§19): заголовки/позиции/сноски/нераспознанные.
CALIBRATION: dict[str, dict[str, int]] = {
    "residential": {"headings": 54, "positions": 266, "footnotes": 2},
    "social": {"headings": 45, "positions": 235, "footnotes": 2},
    "office": {"headings": 51, "positions": 242, "footnotes": 2},
}


@dataclass
class FileReport:
    building_type: str
    sheet_title: str
    hidden_sheets: list[str]
    headings: int = 0
    positions: int = 0
    footnotes: int = 0
    blanks: int = 0
    dash_cells: int = 0
    requirement_cells: int = 0
    vendor_tokens: int = 0
    listings_by_status: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    files: list[FileReport]
    vendors_unique: int
    agreements: int
    star_occurrences: int
    categories: int
    category_warnings: list[str]

    def render(self) -> str:
        lines: list[str] = ["=== Сид вендор-листов: отчёт прогона ==="]
        for fr in self.files:
            lines += [
                f"\n[{fr.building_type}] лист {fr.sheet_title!r}; "
                f"скрытые пропущены: {fr.hidden_sheets}",
                f"  строки: заголовков={fr.headings} позиций={fr.positions} "
                f"сносок={fr.footnotes} пустых={fr.blanks}",
                f"  ячейки: '-'={fr.dash_cells} требований={fr.requirement_cells} "
                f"токенов-вендоров={fr.vendor_tokens}",
                f"  listing по статусу: {fr.listings_by_status}",
            ]
            for w in fr.warnings:
                lines.append(f"  ⚠ {w}")
        lines += [
            "\n--- Итого ---",
            f"  категорий в дереве: {self.categories}",
            f"  уникальных вендоров: {self.vendors_unique}",
            f"  соглашений (звёзд): {self.agreements}; "
            f"listing со звёздным вендором: {self.star_occurrences}",
        ]
        for w in self.category_warnings:
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    def verify(self) -> list[str]:
        mismatches: list[str] = []
        for fr in self.files:
            expected = CALIBRATION.get(fr.building_type)
            if expected is None:
                continue
            for key in ("headings", "positions", "footnotes"):
                actual = getattr(fr, key)
                if actual != expected[key]:
                    mismatches.append(
                        f"{fr.building_type}.{key}: ожидалось {expected[key]}, получено {actual}"
                    )
        return mismatches
