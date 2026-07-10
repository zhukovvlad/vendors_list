"""SQL-фабрики для db-тестов (SQLAlchemy Core, без ORM — правило CLAUDE.md №1).

Два яруса (spec §4.4):
- Справочный (засеян в 0001): building_type / segment_group / segment — LOOKUP
  существующих строк, не вставка (у них уникальные ключи, слепой INSERT упадёт).
- Незасеянный: category / position / vendor / agreement / listing / release /
  project / project_selection — вставка (коллизий нет, изоляция откатом).

Все вставки идут в общее тест-соединение и откатываются в конце теста.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


# --- Справочный ярус: LOOKUP засеянных строк -------------------------------
async def get_building_type_id(conn: AsyncConnection, code: str = "residential") -> int:
    return (
        await conn.execute(
            text("SELECT id FROM building_type WHERE code = :c"), {"c": code}
        )
    ).scalar_one()


async def get_segment_id(
    conn: AsyncConnection,
    name: str = "Бизнес",
    building_type_code: str = "residential",
) -> int:
    return (
        await conn.execute(
            text(
                "SELECT s.id FROM segment s "
                "JOIN building_type bt ON bt.id = s.building_type_id "
                "WHERE bt.code = :bt AND s.name = :n"
            ),
            {"bt": building_type_code, "n": name},
        )
    ).scalar_one()


# --- Незасеянный ярус: вставка ---------------------------------------------
async def make_category(
    conn: AsyncConnection, name: str = "Раздел", parent_id: int | None = None
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO category (name, parent_id) VALUES (:n, :p) RETURNING id"),
            {"n": name, "p": parent_id},
        )
    ).scalar_one()


async def make_position(
    conn: AsyncConnection, category_id: int, name: str = "Позиция"
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO position (category_id, name) VALUES (:c, :n) RETURNING id"),
            {"c": category_id, "n": name},
        )
    ).scalar_one()


async def make_vendor(
    conn: AsyncConnection,
    name: str,
    kind: str = "manufacturer",
    represents_id: int | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO vendor (name, kind, represents_id) "
                "VALUES (:n, :k, :r) RETURNING id"
            ),
            {"n": name, "k": kind, "r": represents_id},
        )
    ).scalar_one()


async def make_agreement(
    conn: AsyncConnection, vendor_id: int, status: str = "active"
) -> int:
    return (
        await conn.execute(
            text("INSERT INTO agreement (vendor_id, status) VALUES (:v, :s) RETURNING id"),
            {"v": vendor_id, "s": status},
        )
    ).scalar_one()


async def make_listing(
    conn: AsyncConnection,
    position_id: int,
    segment_id: int,
    vendor_id: int | None = None,
    status: str = "allowed",
    spec_text: str | None = None,
    sort_order: int = 0,
) -> int:
    """Вставка строки перечня. ВНИМАНИЕ на CHECK listing_status_chk:
    allowed → vendor_id задан, spec_text=None; requirement → vendor_id=None,
    spec_text задан; not_applicable/undefined → vendor_id=None."""
    return (
        await conn.execute(
            text(
                "INSERT INTO listing "
                "(position_id, segment_id, vendor_id, status, spec_text, sort_order) "
                "VALUES (:p, :s, :v, :st, :spec, :ord) RETURNING id"
            ),
            {
                "p": position_id,
                "s": segment_id,
                "v": vendor_id,
                "st": status,
                "spec": spec_text,
                "ord": sort_order,
            },
        )
    ).scalar_one()


async def make_release(
    conn: AsyncConnection,
    building_type_id: int,
    label: str = "ред. тест",
    status: str = "open",
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO release (building_type_id, label, status) "
                "VALUES (:bt, :l, :st) RETURNING id"
            ),
            {"bt": building_type_id, "l": label, "st": status},
        )
    ).scalar_one()


async def make_project(
    conn: AsyncConnection,
    code: str,
    name: str,
    segment_id: int,
    release_id: int | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO compliance.project (code, name, segment_id, release_id) "
                "VALUES (:c, :n, :s, :r) RETURNING id"
            ),
            {"c": code, "n": name, "s": segment_id, "r": release_id},
        )
    ).scalar_one()


async def make_selection(
    conn: AsyncConnection,
    project_id: int,
    position_id: int,
    vendor_id: int,
    rationale: str | None = None,
    source_ref: str | None = None,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO compliance.project_selection "
                "(project_id, position_id, vendor_id, rationale, source_ref) "
                "VALUES (:pr, :po, :v, :ra, :sr) RETURNING id"
            ),
            {
                "pr": project_id,
                "po": position_id,
                "v": vendor_id,
                "ra": rationale,
                "sr": source_ref,
            },
        )
    ).scalar_one()


async def make_building_type(
    conn: AsyncConnection, code: str, name: str = "Тест-тип", sort_order: int = 99
) -> int:
    """Свежий тип объекта (для изоляции агрегатных вьюх — у него нет чужих релизов)."""
    return (
        await conn.execute(
            text(
                "INSERT INTO building_type (code, name, sort_order) "
                "VALUES (:c, :n, :s) RETURNING id"
            ),
            {"c": code, "n": name, "s": sort_order},
        )
    ).scalar_one()


async def make_segment(
    conn: AsyncConnection,
    building_type_id: int,
    name: str = "Тест-класс",
    group_id: int | None = None,
    sort_order: int = 0,
) -> int:
    return (
        await conn.execute(
            text(
                "INSERT INTO segment (building_type_id, group_id, name, sort_order) "
                "VALUES (:bt, :g, :n, :o) RETURNING id"
            ),
            {"bt": building_type_id, "g": group_id, "n": name, "o": sort_order},
        )
    ).scalar_one()


async def make_release_listing(
    conn: AsyncConnection, release_id: int, position_id: int, status: str = "allowed"
) -> int:
    """Минимальная строка снимка издания (release_listing без триггеров)."""
    return (
        await conn.execute(
            text(
                "INSERT INTO release_listing (release_id, position_id, status) "
                "VALUES (:r, :p, :st) RETURNING id"
            ),
            {"r": release_id, "p": position_id, "st": status},
        )
    ).scalar_one()
