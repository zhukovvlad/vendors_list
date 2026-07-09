"""CLI-шим сид-импорта. Логика — в app.seed.loader (там же тесты/типы)."""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys

from app.seed.loader import run

_MASKS = ("*жилые*.xlsx", "*офисные*.xlsx", "*социальные*.xlsx")


def _default_files(temp: str | None = None) -> list[str]:
    if temp is None:
        here = os.path.dirname(os.path.abspath(__file__))
        temp = os.path.normpath(os.path.join(here, "..", "..", "temp"))
    found: list[str] = []
    for mask in _MASKS:
        hits = [p for p in glob.glob(os.path.join(temp, mask)) if "~$" not in p]
        if len(hits) != 1:
            raise RuntimeError(
                f"Ожидался ровно 1 файл по маске {mask!r} в {temp!r}, найдено {len(hits)}: {hits}"
            )
        found.append(hits[0])
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

    if args.files:
        files = args.files
    else:
        try:
            files = _default_files()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if not files:
        print("Не найдены входные файлы (ни аргументов, ни temp/*.xlsx).", file=sys.stderr)
        return 2

    return asyncio.run(
        run(files, dry_run=args.dry_run, author=args.author,
            freeze=args.freeze, force=args.force, verify=args.verify)
    )


if __name__ == "__main__":
    raise SystemExit(main())
