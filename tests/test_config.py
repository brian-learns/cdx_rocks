"""Tests for config.py — manifest loading and resolution."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from cdx_rocks.config import (
    ManifestError,
    load_manifest,
    resolve_catalog_path,
    resolve_rocks_dir,
    resolve_struct_format,
)


def _write_manifest(tmp_path: Path, data: dict) -> Path:
    """Write a cdx-rocks.json manifest and return its path."""
    manifest = tmp_path / "cdx-rocks.json"
    manifest.write_text(
        json.dumps(["cdx-rocks", data]),
        encoding="utf-8",
    )
    return manifest


class TestLoadManifest:
    """load_manifest() reads and validates cdx-rocks.json."""

    def test_valid_minimal(self, tmp_path: Path):
        m = _write_manifest(
            tmp_path,
            {
                "catalog": "catalog.txt",
                "db": "rocks/",
                "struct_format": "!HQI",
            },
        )
        cfg = load_manifest(m)
        assert cfg["catalog"] == str(tmp_path / "catalog.txt")
        assert cfg["db"] == str(tmp_path / "rocks")
        assert cfg["struct_format"] == "!HQI"

    def test_valid_with_iqi(self, tmp_path: Path):
        m = _write_manifest(
            tmp_path,
            {
                "catalog": "cat.zst",
                "db": "db/",
                "struct_format": "!IQI",
            },
        )
        cfg = load_manifest(m)
        assert cfg["struct_format"] == "!IQI"

    def test_rejects_missing_file(self):
        with pytest.raises(ManifestError, match="Manifest not found"):
            load_manifest("/nonexistent/cdx-rocks.json")

    def test_rejects_wrong_tag(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(["wrong-tag", {}]))
        with pytest.raises(ManifestError, match="Expected tag 'cdx-rocks'"):
            load_manifest(path)

    def test_rejects_not_a_list(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"catalog": "x"}))
        with pytest.raises(ManifestError, match="Manifest must be"):
            load_manifest(path)

    def test_rejects_missing_catalog(self, tmp_path: Path):
        m = _write_manifest(tmp_path, {"db": "rocks/", "struct_format": "!HQI"})
        with pytest.raises(ManifestError, match="missing required key 'catalog'"):
            load_manifest(m)

    def test_rejects_missing_db(self, tmp_path: Path):
        m = _write_manifest(tmp_path, {"catalog": "cat.txt", "struct_format": "!HQI"})
        with pytest.raises(ManifestError, match="missing required key 'db'"):
            load_manifest(m)

    def test_rejects_missing_struct_format(self, tmp_path: Path):
        m = _write_manifest(tmp_path, {"catalog": "cat.txt", "db": "rocks/"})
        with pytest.raises(ManifestError, match="missing required key 'struct_format'"):
            load_manifest(m)

    def test_rejects_invalid_struct_format(self, tmp_path: Path):
        m = _write_manifest(
            tmp_path,
            {
                "catalog": "cat.txt",
                "db": "rocks/",
                "struct_format": "!hqi",
            },
        )
        with pytest.raises(ManifestError, match="Invalid struct_format"):
            load_manifest(m)

    def test_absolute_paths_passthrough(self, tmp_path: Path):
        m = _write_manifest(
            tmp_path,
            {
                "catalog": "/abs/catalog.txt",
                "db": "/abs/db/",
                "struct_format": "!HQI",
            },
        )
        cfg = load_manifest(m)
        assert cfg["catalog"] == "/abs/catalog.txt"
        assert cfg["db"] == "/abs/db/"


class TestResolveFunctions:
    """resolve_*() functions require a manifest — no fallbacks."""

    def test_resolve_rocks_dir_from_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _write_manifest(
            tmp_path,
            {
                "catalog": "cat.txt",
                "db": "mydb/",
                "struct_format": "!HQI",
            },
        )
        monkeypatch.setenv("CDX_ROCKS", str(tmp_path))
        assert resolve_rocks_dir() == str(tmp_path / "mydb")

    def test_resolve_catalog_from_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _write_manifest(
            tmp_path,
            {
                "catalog": "my_catalog.zst",
                "db": "rocks/",
                "struct_format": "!HQI",
            },
        )
        monkeypatch.setenv("CDX_ROCKS", str(tmp_path))
        assert resolve_catalog_path() == str(tmp_path / "my_catalog.zst")

    def test_resolve_struct_format_from_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _write_manifest(
            tmp_path,
            {
                "catalog": "cat.txt",
                "db": "rocks/",
                "struct_format": "!IIQ",
            },
        )
        monkeypatch.setenv("CDX_ROCKS", str(tmp_path))
        assert resolve_struct_format() == "!IIQ"

    def test_fallbacks_when_cdx_rocks_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """resolve_*() return safe defaults when CDX_ROCKS is not set."""
        monkeypatch.delenv("CDX_ROCKS", raising=False)
        assert resolve_rocks_dir() == "/data"
        assert resolve_catalog_path() == "/data/all_warc_paths.txt.zst"
        assert resolve_struct_format() == "!HQI"

    def test_raises_when_manifest_not_found(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CDX_ROCKS", "/nonexistent/path")
        with pytest.raises(ManifestError, match="No cdx-rocks.json manifest found"):
            resolve_rocks_dir()

    def test_raises_when_manifest_malformed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bad = tmp_path / "cdx-rocks.json"
        bad.write_text('{"not": "manifest"}')
        monkeypatch.setenv("CDX_ROCKS", str(tmp_path))
        with pytest.raises(ManifestError):
            resolve_rocks_dir()

    def test_resolve_with_explicit_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """resolve_*() accepts an explicit path argument, ignoring env."""
        monkeypatch.setenv("CDX_ROCKS", "/ignored")
        _write_manifest(
            tmp_path,
            {
                "catalog": "explicit.txt",
                "db": "expdb/",
                "struct_format": "<BHI",
            },
        )
        assert resolve_rocks_dir(str(tmp_path)) == str(tmp_path / "expdb")
        assert resolve_catalog_path(str(tmp_path)) == str(tmp_path / "explicit.txt")
        assert resolve_struct_format(str(tmp_path)) == "<BHI"

    def test_manifest_as_direct_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """CDX_ROCKS pointing directly to the JSON file works."""
        manifest = tmp_path / "custom.json"
        manifest.write_text(
            json.dumps(
                [
                    "cdx-rocks",
                    {
                        "catalog": "direct.txt",
                        "db": "directdb/",
                        "struct_format": "!HQI",
                    },
                ]
            )
        )
        monkeypatch.setenv("CDX_ROCKS", str(manifest))
        assert resolve_rocks_dir() == str(tmp_path / "directdb")
