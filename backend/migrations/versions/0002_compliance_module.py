"""Базовая миграция №2: модуль соответствия (схема compliance).

Источник истины — sql/0002_compliance_module.sql (проекты, выбор вендоров,
светофор project_position_status, сводка project_summary). Ядро не меняет,
кроме двух аддитивных индексов.

Revision ID: 0002_compliance
Revises: 0001_core
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op

sys.path.append(str(Path(__file__).resolve().parents[1]))
from _sql import run_sql_file  # noqa: E402

revision = "0002_compliance"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0002_compliance_module.sql")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS compliance CASCADE")
