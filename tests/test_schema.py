"""Tests for schema.py — struct format validation and safe pack/unpack."""

import struct

import pytest

from cdx_rocks.schema import safe_pack, safe_unpack, validate_struct_format


class TestValidateStructFormat:
    """validate_struct_format() accepts exactly [prefix][type][type][type]."""

    @pytest.mark.parametrize("fmt", ["!HQI", "!IQI", "<BHI", ">LQI", "@III", "=BHH", "!IIQ"])
    def test_valid_formats(self, fmt: str):
        assert validate_struct_format(fmt) is True

    def test_rejects_non_string(self):
        assert validate_struct_format(123) is False
        assert validate_struct_format(None) is False  # type: ignore[arg-type]

    def test_rejects_wrong_length(self):
        assert validate_struct_format("!HQ") is False
        assert validate_struct_format("!HQII") is False
        assert validate_struct_format("!") is False

    def test_rejects_missing_prefix(self):
        assert validate_struct_format("HQI") is False

    def test_rejects_signed_types(self):
        assert validate_struct_format("!hqi") is False
        assert validate_struct_format("!bhi") is False

    def test_rejects_floating_point(self):
        assert validate_struct_format("!IQf") is False
        assert validate_struct_format("!IQd") is False

    def test_rejects_string_type(self):
        assert validate_struct_format("!HQs") is False

    def test_rejects_padding(self):
        assert validate_struct_format("!HQx") is False

    def test_rejects_spaces(self):
        assert validate_struct_format("!H QI") is False

    def test_rejects_repeat_counts(self):
        assert validate_struct_format("!3I") is False

    def test_rejects_unknown_prefix(self):
        assert validate_struct_format("xHQI") is False
        assert validate_struct_format("1HQI") is False


class TestSafePack:
    """safe_pack() delegates to struct.pack after validation."""

    def test_pack_valid(self):
        data = safe_pack("!HQI", 1, 2, 3)
        assert isinstance(data, bytes)
        assert len(data) == struct.calcsize("!HQI")

    def test_pack_roundtrips(self):
        data = safe_pack("!HQI", 100, 999_999, 42)
        assert struct.unpack("!HQI", data) == (100, 999_999, 42)

    def test_pack_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unsafe struct format"):
            safe_pack("!hqi", 1, 2, 3)

    def test_pack_wrong_length_raises(self):
        with pytest.raises(ValueError, match="Unsafe struct format"):
            safe_pack("!HQ", 1, 2, 3)


class TestSafeUnpack:
    """safe_unpack() validates format and data length before unpacking."""

    def test_unpack_valid(self):
        data = struct.pack("!HQI", 1, 2, 3)
        result = safe_unpack("!HQI", data)
        assert result == (1, 2, 3)

    def test_unpack_safe_pack_roundtrip(self):
        original = (5, 12345, 67890)
        packed = safe_pack("!HQI", *original)
        assert safe_unpack("!HQI", packed) == original

    def test_unpack_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unsafe struct format"):
            safe_unpack("!hqi", b"\x00" * 16)

    def test_unpack_wrong_data_length_raises(self):
        with pytest.raises(ValueError, match="Expected"):
            safe_unpack("!HQI", b"\x00" * 10)

    def test_unpack_empty_data_raises(self):
        with pytest.raises(ValueError, match="Expected"):
            safe_unpack("!HQI", b"")
