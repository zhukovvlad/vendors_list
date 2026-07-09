from __future__ import annotations

import pytest

from app.seed.parse import (
    CategoryTree,
    CellListing,
    ParsedVendor,
    RowKind,
    SeedError,
    classify_cell,
    classify_row,
    match_requirement,
    parse_heading_number,
    parse_vendor_token,
    split_vendor_tokens,
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
