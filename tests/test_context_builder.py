"""Read-only context selection tests."""

from pathlib import Path

import pytest

from sf_factory.context_builder import build_context


def test_selects_only_explicit_files_within_budget(tmp_path: Path):
    (tmp_path / "a.py").write_text("hello", encoding="utf-8")
    (tmp_path / "b.py").write_text("world!", encoding="utf-8")
    result = build_context(tmp_path, ["a.py", "b.py", "a.py"], max_characters=5)
    assert result.files == (("a.py", "hello"),)
    assert result.excluded == ("b.py",)
    assert result.characters == 5


def test_rejects_parent_traversal(tmp_path: Path):
    assert build_context(tmp_path, ["../outside"]).excluded == ("../outside",)


def test_rejects_symlinks(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("secret", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)
    assert build_context(tmp_path, ["link.txt"]).excluded == ("link.txt",)


def test_rejects_non_utf8(tmp_path: Path):
    (tmp_path / "binary").write_bytes(bytes([255]))
    assert build_context(tmp_path, ["binary"]).excluded == ("binary",)


def test_rejects_negative_budget(tmp_path: Path):
    with pytest.raises(ValueError):
        build_context(tmp_path, [], max_characters=-1)


def test_rejects_nul_containing_file(tmp_path: Path):
    (tmp_path / "mixed.txt").write_bytes(b"hello\\x00world")
    assert build_context(tmp_path, ["mixed.txt"]).excluded == ("mixed.txt",)


def test_rejects_nested_directory_symlink(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "file.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    assert build_context(tmp_path, ["alias/file.txt"]).excluded == ("alias/file.txt",)


def test_rejects_absolute_and_missing_paths(tmp_path: Path):
    paths = [str(tmp_path / "missing"), "missing"]
    assert build_context(tmp_path, paths).excluded == tuple(paths)
