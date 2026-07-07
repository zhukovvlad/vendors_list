"""Выгрузка OpenAPI-схемы FastAPI в файл (для генерации TS-типов в CI/локально).

Не поднимает сервер и не ходит в БД — берёт схему прямо из приложения.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> None:
    OUT.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI schema -> {OUT}")


if __name__ == "__main__":
    main()
