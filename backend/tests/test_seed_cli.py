"""DB-free тесты CLI-шима: guard дефолтных файлов (ровно 1 на маску, §2 ревью)
и страховка --yes для боевой записи."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.seed_vendors as sv
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


# --- Страховка --yes: боевая запись только с явным подтверждением ---


def _spy_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Подменяет loader.run на заглушку, фиксирующую факт и аргументы вызова."""
    captured: dict[str, object] = {}

    async def fake_run(paths: list[str], **kwargs: object) -> int:
        captured["called"] = True
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(sv, "run", fake_run)
    return captured


def test_main_refuses_real_write_without_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _spy_run(monkeypatch)
    monkeypatch.setattr("sys.argv", ["seed_vendors", "a.xlsx"])  # ни --dry-run, ни --yes

    rc = sv.main()

    assert rc == 2
    assert "called" not in captured  # run() НЕ вызван — записи в БД нет


def test_main_dry_run_allowed_without_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _spy_run(monkeypatch)
    monkeypatch.setattr("sys.argv", ["seed_vendors", "a.xlsx", "--dry-run"])

    rc = sv.main()

    assert rc == 0
    assert captured["called"] is True
    assert captured["kwargs"]["dry_run"] is True  # type: ignore[index]


def test_main_yes_allows_real_write(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _spy_run(monkeypatch)
    monkeypatch.setattr("sys.argv", ["seed_vendors", "a.xlsx", "--yes"])

    rc = sv.main()

    assert rc == 0
    assert captured["called"] is True
    assert captured["kwargs"]["dry_run"] is False  # type: ignore[index]
