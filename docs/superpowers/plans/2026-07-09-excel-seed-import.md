# Excel Seed-Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разовый консольный сид `python -m scripts.seed_vendors`, грузящий 3 стартовых Excel-файла в живые таблицы ядра (`category`, `position`, `vendor`, `agreement`, `listing`), идемпотентный, с `--dry-run`.

**Architecture:** Три слоя с жёстким разделением: `app/seed/parse.py` — чистые функции (str/list → dataclass, без openpyxl/БД); `app/seed/reader.py` — чтение xlsx (openpyxl); `app/seed/loader.py` — сборка плана (DB-free) + запись (async SQLAlchemy Core). `app/seed/report.py` — отчёт. CLI-шим — `scripts/seed_vendors.py`. Dry-run НЕ подключается к БД (парсинг + отчёт).

**Tech Stack:** Python 3.12, SQLAlchemy Core (async, asyncpg), openpyxl, argparse, pytest (без БД), ruff, mypy --strict. Всё через `uv`/`just`.

**Спека:** [docs/superpowers/specs/2026-07-09-excel-seed-import-design.md](../specs/2026-07-09-excel-seed-import-design.md). Ссылки §N ниже — на неё.

## Global Constraints

- **Схема БД — источник истины.** Скрипт только раскладывает данные; НЕ пересчитывает светофор/звезду/проценты. Ничего не пишем в `created_by`/`updated_at`/`change_log` вручную — это делают триггеры ядра.
- **`building_type`/`segment`/`segment_group` уже засеяны** миграцией `0001` (стр. 432–466). Сид их не создаёт — делает lookup по имени.
- **Авторство:** транзакция ПЕРВЫМ запросом ставит `app.user` через `set_config('app.user', :login, true)` — bind-параметром, не конкатенацией (дефолт логина `seed`).
- **Ветка:** `feat/excel-seed-import` (уже создана; спека закоммичена). В `main` не коммитить. Каждый таск — свой коммит.
- **Идемпотентность:** один прогон = полная транзакционная перезагрузка стандартов. Сброс — **DELETE в FK-порядке** (НЕ `TRUNCATE … CASCADE`), чтобы гарантированно не задеть `compliance.project` / `compliance.project_selection` (§14, требование ревьюера).
- **mypy --strict** чист: логика в `app/seed` (под `mypy app`), CLI в `scripts` тривиальный. Для openpyxl добавить override `ignore_missing_imports`.
- **Кириллица в выводе:** `just`-рецепты уже форсируют UTF-8; ad-hoc прогоны через Bash — с `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`.
- **Требования (whole-cell markers):** ровно `Россия` (точное) и `По согласованию…` (префикс). `ГОСТ` — НЕ маркер.

---

## File Structure

| Файл | Ответственность |
|------|-----------------|
| `backend/app/seed/__init__.py` | пакет (пустой) |
| `backend/app/seed/parse.py` | чистые функции: классификация строк/ячеек, разбор токена, дерево категорий |
| `backend/app/seed/reader.py` | openpyxl: выбор листа, детекция шапки, границы колонок, разворот merge |
| `backend/app/seed/report.py` | аккумулятор счётчиков/предупреждений + рендер + verify |
| `backend/app/seed/loader.py` | `build_load` (DB-free план) + `execute`/`run` (запись, транзакция, guard, freeze) |
| `backend/scripts/seed_vendors.py` | CLI-шим (argparse → `asyncio.run(loader.run(...))`) |
| `backend/tests/test_seed_parse.py` | Слой 1: юниты чистых функций (без файлов/БД) |
| `backend/tests/test_seed_reader.py` | Слой 2: синтетический xlsx во временной директории |
| `backend/tests/test_seed_loader.py` | Слой 1: `build_load` над синтетическими файлами (без БД) |
| `backend/pyproject.toml` | + mypy override для openpyxl |
| `justfile` | + `seed`, `seed-verify` |

Порядок тасков соответствует зависимостям: parse (1–4) → reader (5) → report (6) → build_load (7) → execute/run (8) → CLI/just (9) → интеграция/девлог (10).

---

### Task 1: parse.py — классификация строк

**Files:**
- Create: `backend/app/seed/__init__.py` (пустой)
- Create: `backend/app/seed/parse.py`
- Test: `backend/tests/test_seed_parse.py`

**Interfaces:**
- Produces: `SeedError(Exception)`; `RowKind(Enum)` {HEADING, POSITION, FOOTNOTE, BLANK}; `RowClass(kind, number: tuple[int,...]|None, name: str|None, source_ref: str|None)`; `classify_row(col_a: object, col_b: object, *, row_no: int) -> RowClass`; `parse_heading_number(prefix: str) -> tuple[int,...]`; helper `_text(v: object) -> str`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_seed_parse.py`:

```python
from __future__ import annotations

import pytest

from app.seed.parse import (
    RowClass,
    RowKind,
    SeedError,
    classify_row,
    parse_heading_number,
)


@pytest.mark.parametrize(
    ("a", "b", "kind", "number", "name"),
    [
        ("1. Оборудование", None, RowKind.HEADING, (1,), "Оборудование"),
        ("1.1. Инженерное оборудование", "", RowKind.HEADING, (1, 1), "Инженерное оборудование"),
        ("1.1.1. Отопление", None, RowKind.HEADING, (1, 1, 1), "Отопление"),
        (1, "Пластинчатый теплообменник", RowKind.POSITION, None, "Пластинчатый теплообменник"),
        ("=A8+1", "Насос", RowKind.POSITION, None, "Насос"),  # контракт parse для формулы-строки; reader (data_only=True) её не отдаёт
        ("Примечание: Ujin — интеграция", None, RowKind.FOOTNOTE, None, None),
        (None, None, RowKind.BLANK, None, None),
        ("", "", RowKind.BLANK, None, None),
    ],
)
def test_classify_row(a: object, b: object, kind: RowKind, number: object, name: object) -> None:
    rc = classify_row(a, b, row_no=9)
    assert rc.kind is kind
    assert rc.number == number
    assert rc.name == name


def test_position_source_ref_is_raw_a() -> None:
    assert classify_row(7, "ТРВ", row_no=94).source_ref == "7"


def test_parse_heading_number_drops_trailing_dot() -> None:
    assert parse_heading_number("1.1.1") == (1, 1, 1)


def test_unrecognized_row_raises_with_location() -> None:
    with pytest.raises(SeedError, match="Строка 42"):
        classify_row("мусор без номера", "", row_no=42)


def test_content_in_a_empty_b_not_heading_raises() -> None:
    with pytest.raises(SeedError):
        classify_row("Просто текст", None, row_no=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.seed'`.

- [ ] **Step 3: Create the package and implement**

`backend/app/seed/__init__.py`: пустой файл.

`backend/app/seed/parse.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q`
Expected: PASS (все параметры).

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/__init__.py backend/app/seed/parse.py backend/tests/test_seed_parse.py
git commit -m "feat(seed): классификация строк файла (heading/position/footnote/blank)"
```

---

### Task 2: parse.py — разбор вендор-токена

**Files:**
- Modify: `backend/app/seed/parse.py` (добавить в конец)
- Test: `backend/tests/test_seed_parse.py` (добавить)

**Interfaces:**
- Consumes: `_text` (Task 1).
- Produces: `ParsedVendor(name: str, starred: bool, ujin: bool, note: str|None)`; `parse_vendor_token(token: str) -> ParsedVendor`; helper `_collapse_ws(s: str) -> str`; константа `_SCOPE_MARKERS`.

- [ ] **Step 1: Write the failing test** — добавить в `test_seed_parse.py`:

```python
from app.seed.parse import ParsedVendor, parse_vendor_token


@pytest.mark.parametrize(
    ("token", "name", "starred", "ujin", "note"),
    [
        ("ИСТРАТЕХ* (Grundfos)", "ИСТРАТЕХ (Grundfos)", True, False, None),
        ("Helmer (SystemAir*)", "Helmer (SystemAir)", True, False, None),
        ("Midea (Bosch, Clivet)", "Midea (Bosch, Clivet)", False, False, None),
        ("STRAZH (RUBEZH)*Ujin", "STRAZH (RUBEZH)", True, True, None),
        ("MasterScada ERMUjin", "MasterScada ERM", False, True, None),
        ("Ujin", "Ujin", False, False, None),  # одиночный Ujin → вендор, не флаг (§9.3)
        ("АРКТИКА (для тех. помещений)", "АРКТИКА", False, False, "для тех. помещений"),
        ("Арктика (паркинг)", "Арктика", False, False, "паркинг"),
        ('"ЭМ-Кабель"*', '"ЭМ-Кабель"', True, False, None),  # кавычки не срезаем (§9.5)
    ],
)
def test_parse_vendor_token(
    token: str, name: str, starred: bool, ujin: bool, note: object
) -> None:
    pv = parse_vendor_token(token)
    assert pv == ParsedVendor(name=name, starred=starred, ujin=ujin, note=note)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q -k vendor_token`
Expected: FAIL — `ImportError: cannot import name 'ParsedVendor'`.

- [ ] **Step 3: Implement** — добавить в `parse.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/parse.py backend/tests/test_seed_parse.py
git commit -m "feat(seed): разбор вендор-токена (звезда/Ujin/скобки-область/кавычки)"
```

---

### Task 3: parse.py — классификация ячейки

**Files:**
- Modify: `backend/app/seed/parse.py`
- Test: `backend/tests/test_seed_parse.py`

**Interfaces:**
- Consumes: `parse_vendor_token`, `_collapse_ws` (Task 2).
- Produces: `CellListing(status: str, vendor_name: str|None, starred: bool, ujin: bool, spec_text: str|None, note: str|None, sort_order: int)`; `match_requirement(text: str) -> bool`; `split_vendor_tokens(cell_text: str) -> list[str]`; `classify_cell(cell_text: str) -> list[CellListing]`. `status` ∈ {`allowed`, `requirement`, `not_applicable`}.

- [ ] **Step 1: Write the failing test** — добавить:

```python
from app.seed.parse import CellListing, classify_cell, match_requirement, split_vendor_tokens


def test_dash_cell() -> None:
    out = classify_cell("-")
    assert out == [CellListing("not_applicable", None, False, False, None, None, 0)]


def test_requirement_whole_cell() -> None:
    assert classify_cell("Россия") == [
        CellListing("requirement", None, False, False, "Россия", None, 0)
    ]
    assert classify_cell("По согласованию с Мосэнергосбыт")[0].status == "requirement"


def test_gost_is_not_a_requirement() -> None:
    # ГОСТ встречается только внутри названий продуктов, не как маркер-ячейка
    assert not match_requirement("Трубы стальные ГОСТ 3262-75")


def test_comma_inside_parens_does_not_split() -> None:
    assert split_vendor_tokens("Midea (Bosch, Clivet)") == ["Midea (Bosch, Clivet)"]


def test_vendor_list_sort_order() -> None:
    out = classify_cell("Ридан, SWEP, ТеплоСила*")
    assert [(c.vendor_name, c.sort_order, c.starred) for c in out] == [
        ("Ридан", 0, False),
        ("SWEP", 1, False),
        ("ТеплоСила", 2, True),
    ]
    assert all(c.status == "allowed" for c in out)


def test_mixed_cell_requirement_into_note() -> None:
    # 'Россия, <вендоры>' → список вендоров + 'Требование: Россия' в note каждого (§8.4)
    out = classify_cell("Россия, Aquatherm green pipe sdr11*, sdr9(faser)")
    assert [c.vendor_name for c in out] == ["Aquatherm green pipe sdr11", "sdr9(faser)"]
    assert all(c.note == "Требование: Россия" for c in out)
    assert out[0].starred is True
    # инвариант ячейки: смешанная ячейка даёт ТОЛЬКО allowed-строки, без мета-строки
    # (иначе триггер listing_cell_chk отверг бы вендоры + мета вместе)
    assert all(c.status == "allowed" for c in out)
    assert all(c.vendor_name is not None and c.spec_text is None for c in out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q -k "cell or requirement or split"`
Expected: FAIL — `ImportError: cannot import name 'CellListing'`.

- [ ] **Step 3: Implement** — добавить в `parse.py`:

```python
DASHES = frozenset({"-", "—", "–"})
_REQ_EXACT = frozenset({"россия"})
_REQ_PREFIX = ("по согласованию",)
_TOKEN_SPLIT = re.compile(r",(?![^(]*\))")


@dataclass(frozen=True)
class CellListing:
    status: str
    vendor_name: str | None
    starred: bool
    ujin: bool
    spec_text: str | None
    note: str | None
    sort_order: int


def match_requirement(text: str) -> bool:
    low = _collapse_ws(text).lower()
    return low in _REQ_EXACT or low.startswith(_REQ_PREFIX)


def split_vendor_tokens(cell_text: str) -> list[str]:
    return [t.strip() for t in _TOKEN_SPLIT.split(cell_text) if t.strip()]


def classify_cell(cell_text: str) -> list[CellListing]:
    text = cell_text.strip()
    if text in DASHES:
        return [CellListing("not_applicable", None, False, False, None, None, 0)]
    if match_requirement(text):
        return [CellListing("requirement", None, False, False, text, None, 0)]
    tokens = split_vendor_tokens(text)
    req_note: str | None = None
    if len(tokens) > 1 and match_requirement(tokens[0]):
        req_note = f"Требование: {tokens[0]}"
        tokens = tokens[1:]
    out: list[CellListing] = []
    for i, tok in enumerate(tokens):
        pv = parse_vendor_token(tok)
        note = pv.note
        if req_note:
            note = f"{req_note}; {note}" if note else req_note
        out.append(CellListing("allowed", pv.name, pv.starred, pv.ujin, None, note, i))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/parse.py backend/tests/test_seed_parse.py
git commit -m "feat(seed): классификация ячейки (прочерк/требование/список вендоров + смешанные)"
```

---

### Task 4: parse.py — дерево категорий

**Files:**
- Modify: `backend/app/seed/parse.py`
- Test: `backend/tests/test_seed_parse.py`

**Interfaces:**
- Consumes: `SeedError` (Task 1).
- Produces: `CategoryNode(number: tuple[int,...], name: str, parent: tuple[int,...]|None, sort_order: int)`; класс `CategoryTree` с методами `add(number: tuple[int,...], name: str, *, file_label: str) -> None`, `integrity_check() -> None`, `ordered() -> list[CategoryNode]` (родители раньше детей) и полем `warnings: list[str]`.

- [ ] **Step 1: Write the failing test** — добавить:

```python
from app.seed.parse import CategoryNode, CategoryTree


def test_category_tree_parent_and_order() -> None:
    t = CategoryTree()
    t.add((1,), "Оборудование", file_label="жилой")
    t.add((1, 1), "Инженерное оборудование", file_label="жилой")
    t.add((1, 1, 1), "Отопление", file_label="жилой")
    nodes = t.ordered()
    assert [n.number for n in nodes] == [(1,), (1, 1), (1, 1, 1)]
    assert nodes[2].parent == (1, 1)
    assert nodes[0].parent is None
    assert nodes[1].sort_order == 1


def test_category_dedup_by_number_first_name_wins_and_warns() -> None:
    t = CategoryTree()
    t.add((1, 1, 1), "Отопление, Вентиляция и Кондиционирование", file_label="жилой")
    t.add((1, 1, 1), "Отопление, Вентиляция и кондиционирование", file_label="соц")
    assert len([n for n in t.ordered() if n.number == (1, 1, 1)]) == 1
    assert t.ordered()[0].name == "Отопление, Вентиляция и Кондиционирование"
    assert any("1.1.1" in w for w in t.warnings)


def test_category_broken_tree_raises() -> None:
    t = CategoryTree()
    t.add((2, 4), "Благоустройство", file_label="офис")  # нет родителя (2,)
    with pytest.raises(SeedError, match="2.4"):
        t.integrity_check()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q -k category`
Expected: FAIL — `ImportError: cannot import name 'CategoryTree'`.

- [ ] **Step 3: Implement** — добавить в `parse.py`:

```python
@dataclass(frozen=True)
class CategoryNode:
    number: tuple[int, ...]
    name: str
    parent: tuple[int, ...] | None
    sort_order: int


class CategoryTree:
    """Объединённое дерево разделов. Идентичность узла — числовой путь (§6)."""

    def __init__(self) -> None:
        self._nodes: dict[tuple[int, ...], CategoryNode] = {}
        self.warnings: list[str] = []

    def add(self, number: tuple[int, ...], name: str, *, file_label: str) -> None:
        existing = self._nodes.get(number)
        if existing is not None:
            if existing.name != name:
                path = ".".join(str(x) for x in number)
                self.warnings.append(
                    f"Категория {path}: конфликт имени ({file_label} даёт {name!r}, "
                    f"оставлено {existing.name!r})"
                )
            return
        parent = number[:-1] if len(number) > 1 else None
        self._nodes[number] = CategoryNode(number, name, parent, number[-1])

    def integrity_check(self) -> None:
        for number in self._nodes:
            if len(number) > 1 and number[:-1] not in self._nodes:
                path = ".".join(str(x) for x in number)
                raise SeedError(f"Дерево разорвано: у узла {path} нет родителя")

    def ordered(self) -> list[CategoryNode]:
        return [self._nodes[k] for k in sorted(self._nodes)]  # префиксный порядок = родители раньше
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/parse.py backend/tests/test_seed_parse.py
git commit -m "feat(seed): дерево категорий (идентичность по числовому пути, целостность)"
```

---

### Task 5: reader.py — чтение xlsx

**Files:**
- Create: `backend/app/seed/reader.py`
- Modify: `backend/pyproject.toml` (mypy override для openpyxl)
- Test: `backend/tests/test_seed_reader.py`

**Interfaces:**
- Consumes: `RowClass`, `RowKind`, `classify_row`, `SeedError`, `_text` (Task 1).
- Produces: `ClassColumn(col: int, segment_name: str, group_name: str|None)`; `ReadRow(row_no: int, row: RowClass, cells: dict[int, str])`; `SheetData(building_type: str, sheet_title: str, hidden_sheets: list[str], classes: list[ClassColumn], rows: list[ReadRow])`; `detect_building_type(path: str) -> str`; `read_workbook(path: str) -> SheetData`.

- [ ] **Step 1: Add mypy override** — в `backend/pyproject.toml` после блока `[tool.mypy]`:

```toml
[[tool.mypy.overrides]]
module = "openpyxl.*"
ignore_missing_imports = true
```

- [ ] **Step 2: Write the failing test** — `backend/tests/test_seed_reader.py`:

```python
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.seed.parse import RowKind
from app.seed.reader import detect_building_type, read_workbook


def test_detect_building_type() -> None:
    assert detect_building_type(r"c:\x\...жилые здания....xlsx") == "residential"
    assert detect_building_type("офисные, ТРЦ.xlsx") == "office"
    assert detect_building_type("социальные объекты.xlsx") == "social"


def _make_book(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Производители"
    ws["A5"] = "№"
    ws["B5"] = "Наименование"
    ws["C5"] = "Комфорт"
    ws.cell(row=5, column=100, value="ФАНТОМ")  # далёкая колонка — не должна читаться
    ws["A6"] = "1. Оборудование"               # heading (B пусто)
    ws["A7"] = 1
    ws["B7"] = "Насос"
    ws["C7"] = "\n Grundfos"                    # ведущий \n снимается
    ws["A8"] = 2
    ws["B8"] = "Клапан"
    # вертикальный merge C7:C8 — значение из C7 должно попасть в позицию строки 8
    ws.merge_cells("C7:C8")
    hidden = wb.create_sheet("Vendor list")
    hidden.sheet_state = "hidden"
    wb.save(path)


def test_read_workbook(tmp_path: Path) -> None:
    p = tmp_path / "тест жилые.xlsx"
    _make_book(p)
    data = read_workbook(str(p))

    assert data.building_type == "residential"
    assert data.hidden_sheets == ["Vendor list"]
    # границы колонок по шапке, НЕ по max_column (фантом в C=col100 игнорируется)
    assert [c.col for c in data.classes] == [3]
    assert data.classes[0].segment_name == "Комфорт"

    positions = [r for r in data.rows if r.row.kind is RowKind.POSITION]
    assert len(positions) == 2
    assert positions[0].cells[3] == "Grundfos"          # ведущий \n снят
    assert positions[1].cells[3] == "Grundfos"          # merge C7:C8 развёрнут
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_reader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.seed.reader'`.

- [ ] **Step 4: Implement** — `backend/app/seed/reader.py`:

```python
"""Чтение сид-книг openpyxl: видимый лист, детекция шапки, границы колонок,
разворот объединённых ячеек для колонок классов. Классификация строк — из parse."""

from __future__ import annotations

import os
from dataclasses import dataclass

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from .parse import RowClass, RowKind, SeedError, _text, classify_row

_BT_BY_SUBSTR = (("жил", "residential"), ("офис", "office"), ("социальн", "social"))
_MAX_HEADER_SCAN = 30
_MAX_CLASS_COL = 40  # верхняя граница поиска классов (защита от фантомных 16384)


@dataclass(frozen=True)
class ClassColumn:
    col: int
    segment_name: str
    group_name: str | None


@dataclass
class ReadRow:
    row_no: int
    row: RowClass
    cells: dict[int, str]


@dataclass
class SheetData:
    building_type: str
    sheet_title: str
    hidden_sheets: list[str]
    classes: list[ClassColumn]
    rows: list[ReadRow]


def detect_building_type(path: str) -> str:
    low = os.path.basename(path).lower()
    for sub, code in _BT_BY_SUBSTR:
        if sub in low:
            return code
    raise SeedError(f"Не определён тип объекта по имени файла: {path!r}")


def _merge_anchors(ws: Worksheet, max_col: int) -> dict[tuple[int, int], tuple[int, int]]:
    """(row,col)->(anchor_row,anchor_col) только для merge в колонках классов (col>=3)."""
    lut: dict[tuple[int, int], tuple[int, int]] = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_col < 3 or mr.min_col > max_col:
            continue  # пропускаем заголовочные A:H и фантомные далёкие merge
        anchor = (mr.min_row, mr.min_col)
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, mr.max_col + 1):
                lut[(r, c)] = anchor
    return lut


def _resolve(ws: Worksheet, lut: dict[tuple[int, int], tuple[int, int]], r: int, c: int) -> object:
    anchor = lut.get((r, c))
    if anchor is not None:
        return ws.cell(row=anchor[0], column=anchor[1]).value
    return ws.cell(row=r, column=c).value


def _nearest_left(ws: Worksheet, row: int, col: int) -> str | None:
    for c in range(col, 2, -1):
        v = _text(ws.cell(row=row, column=c).value)
        if v:
            return v
    return None


def read_workbook(path: str) -> SheetData:
    bt = detect_building_type(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    hidden = [ws.title for ws in wb.worksheets if ws.sheet_state != "visible"]
    visibles = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
    if len(visibles) != 1:
        raise SeedError(f"{path}: ожидался один видимый лист, найдено {len(visibles)}")
    ws = visibles[0]

    anchor_row = next(
        (r for r in range(1, min(ws.max_row, _MAX_HEADER_SCAN) + 1)
         if _text(ws.cell(row=r, column=1).value) == "№"),
        None,
    )
    if anchor_row is None:
        raise SeedError(f"{path}: не найдена строка-якорь шапки (№ в колонке A)")

    below_a = _text(ws.cell(row=anchor_row + 1, column=1).value)
    below_b = _text(ws.cell(row=anchor_row + 1, column=2).value)
    below_classes = any(
        _text(ws.cell(row=anchor_row + 1, column=c).value) for c in range(3, _MAX_CLASS_COL)
    )
    two_level = below_a == "" and below_b == "" and below_classes
    class_row = anchor_row + 1 if two_level else anchor_row
    group_row = anchor_row if two_level else None
    data_start = anchor_row + 2 if two_level else anchor_row + 1

    classes: list[ClassColumn] = []
    c = 3
    while c < _MAX_CLASS_COL:
        label = _text(ws.cell(row=class_row, column=c).value)
        if label == "":
            break
        group = _nearest_left(ws, group_row, c) if group_row is not None else None
        classes.append(ClassColumn(c, label, group))
        c += 1
    if not classes:
        raise SeedError(f"{path}: не найдено ни одной колонки класса на строке {class_row}")

    last_col = classes[-1].col
    lut = _merge_anchors(ws, last_col)

    rows: list[ReadRow] = []
    for r in range(data_start, ws.max_row + 1):
        rc = classify_row(ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value, row_no=r)
        cells: dict[int, str] = {}
        if rc.kind is RowKind.POSITION:
            for cc in classes:
                s = _text(_resolve(ws, lut, r, cc.col))
                if s:
                    cells[cc.col] = s
        rows.append(ReadRow(r, rc, cells))
    return SheetData(bt, ws.title, hidden, classes, rows)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_reader.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/seed/reader.py backend/tests/test_seed_reader.py backend/pyproject.toml
git commit -m "feat(seed): чтение xlsx (видимый лист, шапка по якорю, разворот merge)"
```

---

### Task 6: report.py — отчёт прогона

**Files:**
- Create: `backend/app/seed/report.py`
- Test: `backend/tests/test_seed_parse.py` (добавить блок report — тоже без БД/файлов)

**Interfaces:**
- Produces: `FileReport` (dataclass со счётчиками, см. код); `RunReport` с полями `files: list[FileReport]`, `vendors_unique: int`, `agreements: int`, `star_occurrences: int`, `categories: int`, `category_warnings: list[str]`, методами `render() -> str` и `verify() -> list[str]`. `verify()` возвращает список расхождений с жёсткой калибровкой (заголовки/позиции/сноски/нераспознанные).

- [ ] **Step 1: Write the failing test** — добавить в `test_seed_parse.py`:

```python
from app.seed.report import CALIBRATION, FileReport, RunReport


def test_report_render_and_verify() -> None:
    fr = FileReport(building_type="residential", sheet_title="Производители",
                    hidden_sheets=["Vendor list"])
    fr.headings = 54
    fr.positions = 266
    fr.footnotes = 2
    fr.blanks = 3
    fr.dash_cells = 66
    fr.requirement_cells = 18
    fr.vendor_tokens = 1482
    fr.listings_by_status = {"allowed": 1482, "not_applicable": 66, "requirement": 18}
    rep = RunReport(files=[fr], vendors_unique=300, agreements=120,
                    star_occurrences=582, categories=54, category_warnings=[])
    text = rep.render()
    assert "residential" in text and "266" in text
    # калибровка residential сходится → нет расхождений
    assert rep.verify() == []


def test_report_verify_flags_mismatch() -> None:
    fr = FileReport(building_type="residential", sheet_title="s", hidden_sheets=[])
    fr.headings = 999  # неверно
    fr.positions = CALIBRATION["residential"]["positions"]
    fr.footnotes = 2
    rep = RunReport(files=[fr], vendors_unique=0, agreements=0,
                    star_occurrences=0, categories=0, category_warnings=[])
    assert any("headings" in m for m in rep.verify())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q -k report`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.seed.report'`.

- [ ] **Step 3: Implement** — `backend/app/seed/report.py`:

```python
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
            f"  соглашений (звёзд): {self.agreements}; вхождений '*': {self.star_occurrences}",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_parse.py -q -k report`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/report.py backend/tests/test_seed_parse.py
git commit -m "feat(seed): отчёт прогона (счётчики, рендер, сверка калибровки §19)"
```

---

### Task 7: loader.py — сборка плана (build_load, DB-free)

**Files:**
- Create: `backend/app/seed/loader.py` (без DB-части; она — Task 8)
- Test: `backend/tests/test_seed_loader.py`

**Interfaces:**
- Consumes: `read_workbook`, `SheetData`, `RowKind` (Task 5); `classify_cell`, `CategoryTree`, `CategoryNode` (Tasks 3–4); `FileReport`, `RunReport` (Task 6).
- Produces:
  - `PositionRow(pos_key: int, category_number: tuple[int,...], name: str, source_ref: str|None, sort_order: int)`
  - `ListingRow(pos_key: int, building_type: str, segment_name: str, status: str, vendor_name: str|None, ujin: bool, spec_text: str|None, note: str|None, sort_order: int)`
  - `LoadPlan(categories: list[CategoryNode], positions: list[PositionRow], listings: list[ListingRow], vendors: dict[str, bool], effective_date: dict[str, str|None], report: RunReport)` (`vendors`: имя→starred; `effective_date`: building_type→YYYY-MM-DD|None)
  - `build_load(paths: list[str]) -> LoadPlan`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_seed_loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import openpyxl

from app.seed.loader import build_load


def _make(path: Path, title: str, sheetname: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheetname
    ws["A5"] = "№"
    ws["B5"] = "Наименование"
    ws["C5"] = "Комфорт"
    ws["A6"] = "1. Оборудование"
    ws["A7"] = "1.1. Отопление"
    ws["A8"] = 1
    ws["B8"] = "Насос"
    ws["C8"] = "Ридан, ТеплоСила*"
    ws["A9"] = 2
    ws["B9"] = "Клапан"
    ws["C9"] = "-"
    wb.save(path)


def test_build_load_counts_and_stars(tmp_path: Path) -> None:
    p = tmp_path / "тест жилые.xlsx"
    _make(p, "жилой", "Производители")
    plan = build_load([str(p)])

    assert len(plan.positions) == 2
    # listing: 2 вендора (Насос) + 1 мета '-' (Клапан) = 3
    assert len(plan.listings) == 3
    assert plan.vendors == {"Ридан": False, "ТеплоСила": True}
    # дерево: 1 и 1.1
    assert [n.number for n in plan.categories] == [(1,), (1, 1)]
    dash = [ln for ln in plan.listings if ln.status == "not_applicable"]
    assert len(dash) == 1 and dash[0].vendor_name is None


def test_build_load_is_db_free(tmp_path: Path) -> None:
    # build_load не должен требовать DATABASE_URL — вызов не падает без БД
    p = tmp_path / "тест социальные.xlsx"
    _make(p, "соц", "Оборудование ")
    plan = build_load([str(p)])
    assert plan.report.files[0].building_type == "social"


def _make_dup(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Производители"
    ws["A5"] = "№"
    ws["B5"] = "Наименование"
    ws["C5"] = "Комфорт"
    ws["A6"] = "1. Оборудование"
    ws["A7"] = 1
    ws["B7"] = "Насос"
    ws["C7"] = "Ридан, Ридан"  # повтор бренда в одной ячейке
    wb.save(path)


def test_build_load_dedupes_repeated_vendor_in_cell(tmp_path: Path) -> None:
    # uq_listing_cell_vendor: один vendor_id дважды в ячейке недопустим — дубль
    # пропускается, остаётся один listing + предупреждение
    p = tmp_path / "тест жилые.xlsx"
    _make_dup(p)
    plan = build_load([str(p)])
    allowed = [ln for ln in plan.listings if ln.status == "allowed"]
    assert len(allowed) == 1
    assert plan.vendors == {"Ридан": False}
    assert any("повтор вендора" in w for f in plan.report.files for w in f.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_seed_loader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.seed.loader'`.

- [ ] **Step 3: Implement build_load** — `backend/app/seed/loader.py`:

```python
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
    star_occ = sum(1 for ln in listings if ln.status == "allowed" and vendors.get(ln.vendor_name or "", False))
    report = RunReport(
        files=file_reports,
        vendors_unique=len(vendors),
        agreements=sum(1 for v in vendors.values() if v),
        star_occurrences=star_occ,
        categories=len(tree.ordered()),
        category_warnings=tree.warnings,
    )
    return LoadPlan(tree.ordered(), positions, listings, vendors, effective_date, report)


def _pos_without_heading(path: str, rr: ReadRow):  # noqa: ANN202 — вспомогательный
    from .parse import SeedError

    return SeedError(f"{path} строка {rr.row_no}: позиция вне раздела (нет текущего заголовка)")
```

> Примечание: `star_occurrences` здесь считается как число listing-строк со звёздным вендором (ориентир, не жёсткая калибровка). Точное «число вхождений `*` в файле» печатается справочно.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; uv run pytest tests/test_seed_loader.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed/loader.py backend/tests/test_seed_loader.py
git commit -m "feat(seed): сборка плана загрузки build_load (DB-free) из файлов"
```

---

### Task 8: loader.py — запись в БД (execute + run)

**Files:**
- Modify: `backend/app/seed/loader.py` (дописать)
- Test: `backend/tests/db/test_seed_loader.py` (маркер `db`; скип без `DATABASE_URL_TEST`)

**Interfaces:**
- Consumes: `LoadPlan` (Task 7); `app.db.get_engine` (существует, [backend/app/db.py:30](../../../backend/app/db.py)); `app.seed.parse.SeedError`.
- Produces: `async def execute(conn: AsyncConnection, plan: LoadPlan, *, author: str, freeze: bool, force: bool) -> None`; `async def run(paths: list[str], *, dry_run: bool, author: str, freeze: bool, force: bool, verify: bool) -> int` (возвращает exit-code: 0 ок, 1 калибровка/ошибка).

> **Тест:** db-интеграционный (маркер `db`) через фикстуру `db_conn` (откат-изоляция на тест-ветке Neon; скип без `DATABASE_URL_TEST`, поэтому `just ci` локально зелёный, а в CI гоняется на эфемерной ветке). Это обычный TDD: `execute` — новый код; логика БД (триггеры, `uq_listing_cell_vendor`, `freeze_release`) уже есть — тест проверяет их связку с нашим кодом. Покрывает: загрузку+автора, звезду, guard, `--force`-без-каскада-в-compliance, идемпотентность, freeze. Локально без тест-БД тест скипается — тогда его гоняет CI.
>
> **Свойство безопасности `--force` (важно):** сброс через `DELETE` (не `TRUNCATE CASCADE`) означает, что FK `RESTRICT` из `compliance.project.release_id` / `project_selection.(vendor_id|position_id)` **физически не даст** удалить строки ядра, на которые ссылаются проекты: `DELETE` упадёт, транзакция откатится, проекты целы. Т.е. `--force` снимает guard, но снести стандарты «из-под» активных проектов всё равно нельзя — это желаемое поведение (§14), и тест `test_force_does_not_touch_projects` его фиксирует.

- [ ] **Step 1: Write the failing db-test** — `backend/tests/db/test_seed_loader.py`:

```python
"""Интеграция loader.execute против реальной схемы (триггеры/uq-индексы/freeze).
db-тест: гоняется на тест-ветке Neon, скипается без DATABASE_URL_TEST."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.seed.loader import ListingRow, LoadPlan, PositionRow, execute
from app.seed.parse import CategoryNode, SeedError
from app.seed.report import RunReport
from tests import factories as f

pytestmark = pytest.mark.db


def _mini_plan() -> LoadPlan:
    cats = [CategoryNode((1,), "Оборудование", None, 1)]
    positions = [PositionRow(1, (1,), "Насос", "1", 0)]
    listings = [
        ListingRow(1, "residential", "Бизнес", "allowed", "Ридан", False, None, None, 0),
        ListingRow(1, "residential", "Бизнес", "allowed", "ТеплоСила", False, None, None, 1),
    ]
    vendors = {"Ридан": False, "ТеплоСила": True}
    report = RunReport(files=[], vendors_unique=2, agreements=1,
                       star_occurrences=1, categories=1, category_warnings=[])
    return LoadPlan(cats, positions, listings, vendors, {"residential": "2026-03-25"}, report)


async def test_execute_loads_and_attributes_author(db_conn) -> None:
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    rows = (await db_conn.execute(
        text("SELECT created_by FROM listing WHERE status = 'allowed'"))).scalars().all()
    assert len(rows) == 2 and set(rows) == {"seed@test"}  # автор через триггер
    starred = (await db_conn.execute(
        text("SELECT vendor_starred(id) FROM vendor WHERE name = 'ТеплоСила'"))).scalar_one()
    assert starred is True  # звезда → agreement.active → vendor_starred


async def test_execute_guard_blocks_when_projects_exist(db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await f.make_project(db_conn, code="P-guard", name="Проект", segment_id=seg)
    with pytest.raises(SeedError, match="проектами"):
        await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)


async def test_force_does_not_touch_projects(db_conn) -> None:
    # §14: --force снимает guard, но проект (без ссылок на удаляемые строки) выживает
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    proj = await f.make_project(db_conn, code="P-force", name="Проект", segment_id=seg)
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=True)
    survived = (await db_conn.execute(
        text("SELECT count(*) FROM compliance.project WHERE id = :p"), {"p": proj})).scalar_one()
    assert survived == 1


async def test_force_cannot_delete_standards_referenced_by_selection(db_conn) -> None:
    # Если выбор проекта ссылается на вендора/позицию — DELETE ядра падает на FK,
    # транзакция откатывается: снести стандарты «из-под» проекта нельзя даже с --force.
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    cat = await f.make_category(db_conn, name="X")
    pos = await f.make_position(db_conn, category_id=cat, name="Поз")
    v = await f.make_vendor(db_conn, name="V-keep")
    proj = await f.make_project(db_conn, code="P-ref", name="Проект", segment_id=seg)
    await f.make_selection(db_conn, project_id=proj, position_id=pos, vendor_id=v)
    with pytest.raises(DBAPIError):  # FK RESTRICT на vendor/position
        await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=True)


async def test_execute_is_idempotent(db_conn) -> None:
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    n1 = (await db_conn.execute(text("SELECT count(*) FROM listing"))).scalar_one()
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=False, force=False)
    n2 = (await db_conn.execute(text("SELECT count(*) FROM listing"))).scalar_one()
    assert n1 == n2  # reset+reload — повтор не плодит строки


async def test_execute_freeze_publishes_snapshot(db_conn) -> None:
    # закрывает замечание №4: freeze-путь под автотестом
    await execute(db_conn, _mini_plan(), author="seed@test", freeze=True, force=False)
    rel = (await db_conn.execute(text(
        "SELECT id, status FROM release WHERE building_type_id = "
        "(SELECT id FROM building_type WHERE code = 'residential') "
        "ORDER BY id DESC LIMIT 1"))).mappings().one()
    assert rel["status"] == "published"
    snap = (await db_conn.execute(
        text("SELECT vendor_name FROM release_listing WHERE release_id = :r"),
        {"r": rel["id"]})).scalars().all()
    assert "Ридан" in snap
```

- [ ] **Step 2: Run test to verify it fails (or skips locally)**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -q`
Expected: если `DATABASE_URL_TEST` задан — FAIL (`ImportError: cannot import name 'execute'`); если не задан — SKIP. При SKIP локально драйвером выступает CI/Neon; всё равно писать тест первым.

- [ ] **Step 3: Implement execute + run** — дописать в `backend/app/seed/loader.py`:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import get_engine

# Порядок УДАЛЕНИЯ (дети → родители). DELETE, НЕ TRUNCATE CASCADE — чтобы
# гарантированно не задеть compliance.project* (§14, требование ревьюера).
_RESET_ORDER = (
    "release_listing", "release", "listing", "change_log", "agreement_change_log",
    "agreement", "position", "vendor_alias", "vendor", "category",
)


async def _guard_no_projects(conn: AsyncConnection, force: bool) -> None:
    from .parse import SeedError

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


async def _reset(conn: AsyncConnection) -> None:
    for tbl in _RESET_ORDER:
        await conn.execute(text(f"DELETE FROM public.{tbl}"))  # compliance НЕ трогаем


async def execute(
    conn: AsyncConnection, plan: LoadPlan, *, author: str, freeze: bool, force: bool
) -> None:
    from .parse import SeedError

    # 1. Идентичность аудита (SET LOCAL-семантика; логин bind-параметром)
    await conn.execute(text("SELECT set_config('app.user', :u, true)"), {"u": author})
    # 2. Защита + сброс
    await _guard_no_projects(conn, force)
    await _reset(conn)

    # 3. Категории (родители раньше — plan.categories уже упорядочен)
    cat_id: dict[tuple[int, ...], int] = {}
    for node in plan.categories:
        parent_id = cat_id[node.parent] if node.parent is not None else None
        rid = await conn.execute(
            text("INSERT INTO category(parent_id, name, sort_order) "
                 "VALUES (:p, :n, :s) RETURNING id"),
            {"p": parent_id, "n": node.name, "s": node.sort_order},
        )
        cat_id[node.number] = int(rid.scalar_one())

    # 4. Позиции
    pos_id: dict[int, int] = {}
    for pos in plan.positions:
        rid = await conn.execute(
            text("INSERT INTO position(category_id, name, source_ref, sort_order) "
                 "VALUES (:c, :n, :sr, :s) RETURNING id"),
            {"c": cat_id[pos.category_number], "n": pos.name,
             "sr": pos.source_ref, "s": pos.sort_order},
        )
        pos_id[pos.pos_key] = int(rid.scalar_one())

    # 5. Вендоры + соглашения (звезда)
    vendor_id: dict[str, int] = {}
    for name, starred in plan.vendors.items():
        rid = await conn.execute(
            text("INSERT INTO vendor(name) VALUES (:n) RETURNING id"), {"n": name}
        )
        vid = int(rid.scalar_one())
        vendor_id[name] = vid
        if starred:
            await conn.execute(
                text("INSERT INTO agreement(vendor_id, status) VALUES (:v, 'active')"),
                {"v": vid},
            )

    # 6. Карта сегментов (code, segment_name) -> id (справочник уже засеян 0001)
    seg_rows = await conn.execute(
        text("SELECT s.id, s.name, bt.code FROM public.segment s "
             "JOIN public.building_type bt ON bt.id = s.building_type_id")
    )
    seg_id: dict[tuple[str, str], int] = {(r.code, r.name): r.id for r in seg_rows}

    # 7. Листинги (триггеры проставят автора/аудит/инвариант ячейки)
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

    # 8. Опциональная фиксация первого издания (по умолчанию выкл, §13)
    if freeze:
        bt_rows = await conn.execute(text("SELECT id, code FROM public.building_type"))
        bt_id = {r.code: r.id for r in bt_rows}
        present = {ln.building_type for ln in plan.listings}
        for code in present:
            eff = plan.effective_date.get(code)
            label = f"к Стандартам, {eff}" if eff else "к Стандартам (сид)"
            rel = await conn.execute(
                text("INSERT INTO release(building_type_id, label, effective_date, status) "
                     "VALUES (:bt, :l, :d, 'open') RETURNING id"),
                {"bt": bt_id[code], "l": label, "d": eff},
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
        await execute(conn, plan, author=author, freeze=freeze, force=force)
    print("\n✅ Записано в БД.")
    return 0
```

- [ ] **Step 4: Typecheck the module**

Run: `cd backend; uv run mypy app/seed`
Expected: `Success: no issues found`. (Если mypy ругается на `r.code`/`r.id` из Result — добавить локальный `# type: ignore[attr-defined]` на строках маппинга seg_id/bt_id или обращаться по индексу `r[0]/r[1]`.)

- [ ] **Step 5: Run the db-test (passes on Neon; skips locally without test DB)**

Run: `cd backend; uv run pytest tests/db/test_seed_loader.py -q`
Expected: с `DATABASE_URL_TEST` — все PASS; без него — SKIP (тогда зелёный прогон обеспечит CI на эфемерной ветке Neon). Инвертированный TDD: логика БД уже есть — ждём PASS с первого прогона; FAIL = ошибка в нашем `execute`/понимании схемы, БД НЕ правим.

- [ ] **Step 6: Commit**

```bash
git add backend/app/seed/loader.py backend/tests/db/test_seed_loader.py
git commit -m "feat(seed): запись в БД (app.user, guard+DELETE-reset, listing, freeze) + db-тесты"
```

---

### Task 9: CLI-шим + команды just

**Files:**
- Create: `backend/scripts/seed_vendors.py`
- Modify: `justfile` (после рецепта `types`)

**Interfaces:**
- Consumes: `app.seed.loader.run` (Task 8).
- Produces: CLI `python -m scripts.seed_vendors [ФАЙЛЫ...] [--dry-run] [--author L] [--freeze] [--force] [--verify]`; поиск 3 файлов в `../temp` по маске имени при отсутствии позиционных аргументов.

- [ ] **Step 1: Implement CLI** — `backend/scripts/seed_vendors.py`:

```python
"""CLI-шим сид-импорта. Логика — в app.seed.loader (там же тесты/типы)."""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys

from app.seed.loader import run

_MASKS = ("*жилые*.xlsx", "*офисные*.xlsx", "*социальные*.xlsx")


def _default_files() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    temp = os.path.normpath(os.path.join(here, "..", "..", "temp"))
    found: list[str] = []
    for mask in _MASKS:
        hits = [p for p in glob.glob(os.path.join(temp, mask)) if "~$" not in p]
        found.extend(hits)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Сид вендор-листов из Excel в живые таблицы.")
    ap.add_argument("files", nargs="*", help="пути к .xlsx (по умолчанию — 3 файла из temp/)")
    ap.add_argument("--dry-run", action="store_true", help="только разбор+отчёт, БД не трогаем")
    ap.add_argument("--author", default="seed", help="логин для app.user (дефолт seed)")
    ap.add_argument("--freeze", action="store_true", help="заморозить первое издание (дефолт выкл)")
    ap.add_argument("--force", action="store_true", help="перезаписать при существующих проектах")
    ap.add_argument("--verify", action="store_true", help="сверить счётчики с калибровкой §19")
    args = ap.parse_args()

    files = args.files or _default_files()
    if not files:
        print("Не найдены входные файлы (ни аргументов, ни temp/*.xlsx).", file=sys.stderr)
        return 2

    return asyncio.run(
        run(files, dry_run=args.dry_run, author=args.author,
            freeze=args.freeze, force=args.force, verify=args.verify)
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add just recipes** — в `justfile` после рецепта `types` (перед `lint`):

```makefile
# Сид живых таблиц из стартовых Excel (temp/). Пример: just seed --dry-run
seed *args:
    cd {{backend}}; uv run python -m scripts.seed_vendors {{args}}

# Ручная калибровка парсера на 3 реальных файлах (dry-run + сверка). НЕ в CI.
seed-verify:
    cd {{backend}}; uv run python -m scripts.seed_vendors --dry-run --verify
```

- [ ] **Step 3: Smoke the CLI help (no DB)**

Run: `cd backend; uv run python -m scripts.seed_vendors --help`
Expected: печатает usage со всеми флагами, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/seed_vendors.py justfile
git commit -m "feat(seed): CLI-шим scripts.seed_vendors + just seed/seed-verify"
```

---

### Task 10: Интеграция — калибровка, чистота, девлог

**Files:**
- Modify: `CLAUDE.md` (§5 порядок работ — отметить импорт), при необходимости
- Create: `docs/devlog/2026-07-09-excel-seed-import.md`

- [ ] **Step 1: Run full seed test suite**

Run: `cd backend; uv run pytest tests/test_seed_parse.py tests/test_seed_reader.py tests/test_seed_loader.py tests/db/test_seed_loader.py -q`
Expected: юниты (parse/reader/loader) — PASS; db-тест — PASS с `DATABASE_URL_TEST`, иначе SKIP (гоняется в CI на Neon).

- [ ] **Step 2: Lint + typecheck clean**

Run: `cd backend; uv run ruff check .; uv run mypy app`
Expected: ruff — `All checks passed!`; mypy — `Success: no issues found`.

- [ ] **Step 3: Manual calibration smoke (DB-free) over the 3 real files**

Run: `just seed-verify`
Expected: печатается отчёт по 3 файлам; строка `✅ Калибровка сошлась` (заголовки 54/45/51, позиции 266/235/242, сноски 2/2/2). Если расхождение — разбираться в парсере/ридере, БД НЕ трогать (инвертированный TDD, спека §18). Числа `-`/требований/звёзд — сверить глазами с §19 как ориентир.

- [ ] **Step 4: Full CI gate (перед пушем — обязательно, CLAUDE §7)**

Run: `just ci`
Expected: `OK: все проверки прошли` (types, lint, typecheck, test — фронт/бэк).

- [ ] **Step 5: Optional — реальная запись на тест-ветку Neon (если задан DATABASE_URL_TEST)**

Только вручную, не в CI. Прогнать сид на тест-БД, затем повторить — убедиться, что
повторный прогон не падает и число строк `listing` не меняется (идемпотентность).
Команда (пример, из backend): установить окружение на тест-URL и `uv run python -m
scripts.seed_vendors` без `--dry-run`. Зафиксировать наблюдение в девлоге.

Freeze-путь уже под автотестом (`tests/db/test_seed_loader.py::test_execute_freeze_publishes_snapshot`);
здесь — сквозное подтверждение на реальных 3 файлах: один прогон с `--freeze`, затем
`SELECT status, count(*) FROM release r JOIN release_listing rl ON rl.release_id=r.id
GROUP BY 1` (ожидаем `published` на каждый тип объекта, снимок непустой).

- [ ] **Step 6: Write devlog** — `docs/devlog/2026-07-09-excel-seed-import.md`: что сделано, находки скана (маркеры Россия/По согласованию, merge C89:H93, одиночный Ujin), решения ревью (no-freeze, требование-в-note, --force), находки 2-го ревью (дедуп вендора в ячейке против `uq_listing_cell_vendor`), db-тесты Task 8 через `db_conn`/factories + свойство FK-RESTRICT (`--force` не сносит стандарты «из-под» проектов), калибровка. По образцу соседних файлов в `docs/devlog/`.

- [ ] **Step 7: Commit + push + PR**

```bash
git add docs/devlog/2026-07-09-excel-seed-import.md CLAUDE.md
git commit -m "docs(devlog): сид-импорт вендор-листов из Excel"
git push -u origin feat/excel-seed-import
```
Затем PR в `main` (через `gh pr create`), `main` держим зелёным.

---

## Self-Review

**Spec coverage:**
- §2 слои (parse/reader/loader/report) → Tasks 1–8; CLI §17 → Task 9. ✔
- §4 чтение (data_only, лист по visible, шапка по якорю №, границы по шапке, разворот merge, нормализация) → Task 5. ✔
- §5 классификация строк (+BLANK, +ошибка с локацией) → Task 1. ✔
- §6 дерево (числовой путь, конфликт имени → warning, целостность) → Task 4. ✔
- §7 позиции per-file, source_ref, requirements=NULL → Task 7 (`PositionRow`, INSERT без requirements) . ✔
- §8 ячейка (dash/requirement/vendor-list, маркеры Россия/По согласованию, смешанные → note) → Task 3. ✔
- §9 токен (звезда/Ujin/одиночный Ujin/скобки-область/кавычки) → Task 2. ✔
- §10 дедуп вендоров + агрумент по звезде (агрегирование) → Task 7 (`vendors` dict) + Task 8 (agreement). ✔
- §11 маппинг классов → Task 5 (чтение меток) + Task 8 (авторитетная сверка с segment, ошибка со списком). ✔
- §12 listing (статусы, sort_order, опора на триггеры) → Task 8. ✔
- §13 freeze (дефолт выкл, механика есть) → Task 8 (`freeze`) + Task 9 (`--freeze`). ✔
- §14 идемпотентность (guard + DELETE-reset, --force не каскадит в compliance) → Task 8 (`_guard_no_projects`, `_reset`, `_RESET_ORDER` без compliance). ✔
- §15 app.user через set_config bind → Task 8. ✔
- §16 dry-run (DB-free) + отчёт + предупреждения → Tasks 6–8. ✔
- §17 CLI/just → Task 9. ✔
- §18 тесты (слой1 юнит, слой2 синтетический xlsx, слой3 db-интеграция) → Tasks 1–7 (слой1/2), Task 8 (слой3: `tests/db/test_seed_loader.py` через `db_conn`/factories, гоняется в CI на Neon). ✔
- §19 калибровка/verify → Task 6 + Task 10 smoke. ✔

**Placeholder scan:** нет TBD/«handle edge cases»/«similar to Task N» — каждый шаг с полным кодом и командой. Task 8 имеет db-интеграционный тест (`db_conn`/factories, маркер `db`), скипается локально без `DATABASE_URL_TEST`, гоняется в CI на Neon. ✔

**Type consistency:** `CellListing`(Task 3) поля совпадают с использованием в build_load (Task 7). `ParsedVendor`(Task 2) ← `classify_cell`. `CategoryNode.number/parent/sort_order`(Task 4) ← `ordered()` ← execute cat_id (Task 8). `LoadPlan`/`PositionRow`/`ListingRow`(Task 7) ← execute (Task 8) поля совпадают (`pos_key`, `category_number`, `building_type`, `segment_name`, `vendor_name`, `spec_text`, `ujin`, `note`, `sort_order`). `run(...)` сигнатура (Task 8) ← CLI (Task 9) аргументы совпадают. ✔
```
