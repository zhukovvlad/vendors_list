"""DB-free тесты CLI-шима: guard дефолтных файлов (ровно 1 на маску, §2 ревью)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_vendors import _default_files


def _touch(path: Path) -> None:
    path.write_bytes(b"")


def test_default_files_happy_path_one_per_mask(tmp_path: Path) -> None:
    _touch(tmp_path / "2026 жилые дома.xlsx")
    _touch(tmp_path / "2026 офисные центры.xlsx")
    _touch(tmp_path / "2026 социальные объекты.xlsx")

    found = _default_files(str(tmp_path))

    assert len(found) == 3


def test_default_files_duplicate_mask_raises(tmp_path: Path) -> None:
    _touch(tmp_path / "2026 жилые дома.xlsx")
    _touch(tmp_path / "2026 жилые дома (копия).xlsx")  # второй хит по маске "*жилые*"
    _touch(tmp_path / "2026 офисные центры.xlsx")
    _touch(tmp_path / "2026 социальные объекты.xlsx")

    with pytest.raises(RuntimeError):
        _default_files(str(tmp_path))


def test_default_files_missing_mask_raises(tmp_path: Path) -> None:
    _touch(tmp_path / "2026 жилые дома.xlsx")
    _touch(tmp_path / "2026 офисные центры.xlsx")
    # социальные — отсутствуют

    with pytest.raises(RuntimeError):
        _default_files(str(tmp_path))


def test_default_files_ignores_lock_files(tmp_path: Path) -> None:
    _touch(tmp_path / "2026 жилые дома.xlsx")
    _touch(tmp_path / "~$2026 жилые дома.xlsx")  # lock-файл Excel — игнорируется
    _touch(tmp_path / "2026 офисные центры.xlsx")
    _touch(tmp_path / "2026 социальные объекты.xlsx")

    found = _default_files(str(tmp_path))

    assert len(found) == 3
