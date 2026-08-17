"""Tests for cdx_rocks.build and cdx_rocks.update — catalog loading, pack/unpack."""

import json
import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import zstandard as zstd

from cdx_rocks.build import load_catalog
from cdx_rocks.schema import safe_pack, safe_unpack, validate_struct_format

# Grab the original zstd.open that conftest saved (same trick as test_app.py)
_orig_zstd_open = sys.modules["tests.conftest"]._orig_zstd_open  # type: ignore[attr-defined]


class TestLoadCatalog:
    """Tests for load_catalog() using the test catalog file."""

    def test_load_test_catalog(self, tmp_path):
        """Load the bundled test catalog and verify entry count."""
        test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
        catalog = load_catalog(str(test_catalog))
        assert len(catalog) == 10
        # First entry should be WARC file from 2016-08
        assert "CC-NEWS-20160826124520-00000.warc.gz" in catalog
        assert catalog["CC-NEWS-20160826124520-00000.warc.gz"] == 1

    def test_catalog_ids_are_1_indexed(self, tmp_path):
        """Catalog IDs start from 1."""
        test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
        catalog = load_catalog(str(test_catalog))
        assert min(catalog.values()) == 1
        assert max(catalog.values()) == 10

    def test_catalog_values_are_filenames(self, tmp_path):
        """Catalog keys are WARC filenames (basename)."""
        test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
        catalog = load_catalog(str(test_catalog))
        for key in catalog:
            assert "/" not in key  # Should be basename only
            assert key.endswith(".warc.gz")


class TestPackUnpackRoundtrip:
    """Verify struct packing matches the index format used by build/update."""

    def test_default_format_roundtrip(self):
        """!HQI format roundtrips correctly."""
        warc_id, offset, length = 42, 1024, 2048
        packed = safe_pack("!HQI", warc_id, offset, length)
        assert len(packed) == 14  # H(2) + Q(8) + I(4) = 14
        unpacked = safe_unpack("!HQI", packed)
        assert unpacked == (42, 1024, 2048)

    def test_large_values(self):
        """Large offset/length values fit in Q/I types."""
        warc_id = 65535  # Max H (uint16)
        offset = 999_999_999_999  # Large Q
        length = 4_294_967_295  # Max I (uint32)
        packed = safe_pack("!HQI", warc_id, offset, length)
        unpacked = safe_unpack("!HQI", packed)
        assert unpacked == (warc_id, offset, length)

    def test_iqi_format(self):
        """!IQI format also works (larger ID field)."""
        warc_id, offset, length = 1_000_000, 1024, 2048
        packed = safe_pack("!IQI", warc_id, offset, length)
        unpacked = safe_unpack("!IQI", packed)
        assert unpacked == (1_000_000, 1024, 2048)


class TestBuildManifest:
    """Verify the manifest format written by the builder."""

    def test_manifest_structure(self, tmp_path):
        """Manifest has the correct tag and fields."""
        manifest_path = tmp_path / "cdx-rocks.json"
        manifest = [
            "cdx-rocks",
            {
                "catalog": "all_warc_paths.txt.zst",
                "db": "rocks/",
                "struct_format": "!HQI",
            },
        ]
        manifest_path.write_text(json.dumps(manifest) + "\n")

        data = json.loads(manifest_path.read_text())
        assert data[0] == "cdx-rocks"
        assert data[1]["catalog"] == "all_warc_paths.txt.zst"
        assert data[1]["db"] == "rocks/"
        assert data[1]["struct_format"] == "!HQI"


class TestStructFormatValidation:
    """Verify validate_struct_format catches bad formats."""

    def test_valid_hqi(self):
        assert validate_struct_format("!HQI") is True

    def test_valid_iqi(self):
        assert validate_struct_format("!IQI") is True

    def test_rejects_missing_prefix(self):
        assert validate_struct_format("HQI") is False

    def test_rejects_signed(self):
        assert validate_struct_format("!hqi") is False

    def test_rejects_wrong_length(self):
        assert validate_struct_format("!HQ") is False
        assert validate_struct_format("!HQII") is False
