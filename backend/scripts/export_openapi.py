"""Выгрузка OpenAPI-схемы FastAPI в файл (для генерации TS-типов в CI/локально).

Не поднимает сервер и не ходит в БД — берёт схему прямо из приложения.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# export_openapi лишь дампит схему (сервер не поднимает) — файловые логи тут не нужны.
# LOG_TO_FILE=0 ДО импорта app.main: create_app() зовёт setup_logging() на импорте,
# иначе дамп схемы наплодил бы backend/logs. setdefault уважает явный override.
os.environ.setdefault("LOG_TO_FILE", "0")

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> None:
    OUT.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI schema -> {OUT}")


if __name__ == "__main__":
    main()
