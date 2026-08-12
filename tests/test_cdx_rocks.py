"""Tests for src/cdx_rocks/__init__.py — setup_shadow() and CLI."""

from pathlib import Path

import pytest

from cdx_rocks.shadow import setup_shadow

CONFIG_FILENAME = "rocksdict-config.json"


def test_setup_shadow_creates_linksdir(tmp_path: Path) -> None:
    """Shadow dir is created when it does not exist."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "data.db").write_text("data")

    result = setup_shadow(src, dst)
    assert result == dst.resolve()
    assert dst.is_dir()
    assert (dst / "data.db").is_symlink()


def test_setup_shadow_copies_config(tmp_path: Path) -> None:
    """rocksdict-config.json is copied, not symlinked."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / CONFIG_FILENAME).write_text("{}")
    (src / "other.db").write_text("x")

    setup_shadow(src, dst)
    cfg = dst / CONFIG_FILENAME
    assert cfg.exists() and not cfg.is_symlink()
    assert cfg.read_text() == "{}"


def test_setup_shadow_symlinks_other_files(tmp_path: Path) -> None:
    """Non-config files are symlinked."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "000001.log").write_text("wal")
    (src / "CURRENT").write_text("CURRENT")

    setup_shadow(src, dst)
    assert (dst / "000001.log").is_symlink()
    assert (dst / "CURRENT").is_symlink()


def test_setup_shadow_raises_on_missing_source(tmp_path: Path) -> None:
    """FileNotFoundError when source does not exist."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        setup_shadow(tmp_path / "nope", tmp_path / "dst")


def test_setup_shadow_subdirectory_is_symlinked(tmp_path: Path) -> None:
    """Subdirectories inside the DB are also symlinked."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "subdir").mkdir()
    (src / "subdir" / "file.txt").write_text("nested")

    setup_shadow(src, dst)
    assert (dst / "subdir").is_symlink()


def test_setup_shadow_overwrites_existing_target(tmp_path: Path) -> None:
    """Existing files in the target are cleaned up before relinking."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "data.db").write_text("source")
    (dst / "data.db").write_text("stale")

    setup_shadow(src, dst)
    assert (dst / "data.db").is_symlink()


def test_setup_shadow_skips_self_reference(tmp_path: Path) -> None:
    """If linksdir is inside rocksdb_dir, the self-reference is skipped."""
    src = tmp_path / "src"
    dst = src / "shadow"
    src.mkdir()
    (src / "data.db").write_text("x")

    # Should not recurse infinitely
    setup_shadow(src, dst)
    assert (dst / "data.db").is_symlink()
    # shadow/ itself should NOT be symlinked into shadow/
    assert not (dst / "shadow").exists()
