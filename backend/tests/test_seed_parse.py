from __future__ import annotations

import pytest

from app.seed.parse import (
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
        # контракт parse для формулы-строки; reader (data_only=True) её не отдаёт
        ("=A8+1", "Насос", RowKind.POSITION, None, "Насос"),
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
