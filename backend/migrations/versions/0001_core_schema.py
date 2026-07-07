"""Базовая миграция №1: ядро стандартов (схема public).

Источник истины — sql/0001_core_schema.sql (справочники, listing + аудит,
издания + снимки, freeze_release, вьюха listing_live, сиды типов/классов).

Revision ID: 0001_core
Revises:
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from _sql import run_sql_file  # noqa: E402

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0001_core_schema.sql")


def downgrade() -> None:
    # Базовая миграция: откат — снос схемы public целиком не делаем автоматически.
    raise NotImplementedError("Base migration is not reversible; recreate the database")
