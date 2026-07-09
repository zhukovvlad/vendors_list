"""Чистые функции разбора сид-файлов: строки/ячейки/токены/дерево.

НЕ импортирует openpyxl и НЕ ходит в БД — принимает простые str/int/None и
возвращает dataclass. Тестируется таблицей «вход → результат» без файлов.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SeedError(Exception):
    """Нераспознанная строка / разрыв дерева / неизвестный класс — прогон падает."""


class RowKind(Enum):
    HEADING = "heading"
    POSITION = "position"
    FOOTNOTE = "footnote"
    BLANK = "blank"


@dataclass(frozen=True)
class RowClass:
    kind: RowKind
    number: tuple[int, ...] | None = None
    name: str | None = None
    source_ref: str | None = None


_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
_FOOTNOTE_PREFIX = "Примечание: Ujin"


def _text(v: object) -> str:
    return "" if v is None else str(v).strip()


def parse_heading_number(prefix: str) -> tuple[int, ...]:
    return tuple(int(seg) for seg in prefix.split(".") if seg != "")


def _is_position_number(a_raw: object, a: str) -> bool:
    if isinstance(a_raw, bool):
        return False
    if isinstance(a_raw, int):
        return True
    if isinstance(a_raw, float):
        return a_raw.is_integer()
    # a.isdigit() — обычный номер позиции. a.startswith("=") — защитный контракт
    # parse.py для формулы-строки: reader открывает файлы с data_only=True, где
    # формулы уже вычислены в число, поэтому на боевых файлах эта ветка не
    # срабатывает. Оставлена сознательно — parse.py не завязан на режим чтения
    # (тест выше проверяет контракт напрямую). Это НЕ мёртвый код по недосмотру.
    return a.isdigit() or a.startswith("=")


def classify_row(col_a: object, col_b: object, *, row_no: int) -> RowClass:
    a, b = _text(col_a), _text(col_b)
    if a == "" and b == "":
        return RowClass(RowKind.BLANK)
    if a.startswith(_FOOTNOTE_PREFIX):
        return RowClass(RowKind.FOOTNOTE)
    if b == "":
        m = _HEADING_RE.match(a)
        if m:
            return RowClass(
                RowKind.HEADING,
                number=parse_heading_number(m.group(1)),
                name=m.group(2).strip(),
            )
        raise SeedError(f"Строка {row_no}: не распознана (B пусто, A не заголовок): {a!r}")
    if _is_position_number(col_a, a):
        return RowClass(RowKind.POSITION, name=b, source_ref=a)
    raise SeedError(f"Строка {row_no}: не распознана: A={a!r} B={b!r}")


@dataclass(frozen=True)
class ParsedVendor:
    name: str
    starred: bool
    ujin: bool
    note: str | None


_SCOPE_MARKERS = ("для ", "паркинг", "поквартирн", "тех. помещ")
_UJIN = "Ujin"


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip()


def parse_vendor_token(token: str) -> ParsedVendor:
    raw = _collapse_ws(token)
    starred = "*" in raw
    name = raw.replace("*", "")
    ujin = False
    if _UJIN in name:
        stripped = _collapse_ws(name.replace(_UJIN, ""))
        if stripped:  # 'MasterScada ERMUjin' → флаг интеграции, имя = остаток
            ujin = True
            name = stripped
        # else: токен целиком 'Ujin' → вендор 'Ujin', ujin остаётся False (§9.3)
    note: str | None = None
    m = re.search(r"\(([^)]*)\)", name)  # область применения: содержимое ПЕРВОЙ скобки
    if m:
        inner = m.group(1).strip()
        if any(mk in inner.lower() for mk in _SCOPE_MARKERS):
            note = inner
            name = name[: m.start()].strip()
    return ParsedVendor(name=_collapse_ws(name), starred=starred, ujin=ujin, note=note)
