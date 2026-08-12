"""Validate and safely pack/unpack struct format strings.

Exactly 3 unsigned integer types with a required byte-order prefix.
"""

import struct

ALLOWED = set("BHILQ")
VALID_PREFIX = {"@", "=", "<", ">", "!"}


def validate_struct_format(fmt: object) -> bool:
    """Return True if *fmt* is exactly ``[prefix][type][type][type]``.

    Prefix is one of ``@``, ``=``, ``<``, ``>``, ``!`` and is **required**.
    Each type is one of ``B``, ``H``, ``I``, ``L``, ``Q``.
    Rejects spaces, repeat counts, other types, wrong length, missing prefix.
    """
    if not isinstance(fmt, str) or len(fmt) != 4:
        return False

    if fmt[0] not in VALID_PREFIX:
        return False

    if not all(c in ALLOWED for c in fmt[1:]):
        return False

    try:
        struct.calcsize(fmt)
    except struct.error:
        return False

    return True


def safe_pack(fmt: str, v1: int, v2: int, v3: int) -> bytes:
    """Pack 3 unsigned integer values with a validated struct format.

    Raises ``ValueError`` if *fmt* is not a valid 4-character format string.
    """
    if not validate_struct_format(fmt):
        raise ValueError(f"Unsafe struct format: {fmt!r}")
    return struct.pack(fmt, v1, v2, v3)


def safe_unpack(fmt: str, data: bytes) -> tuple[int, int, int]:
    """Unpack 3 unsigned integer values from *data* using a validated format.

    Raises ``ValueError`` if *fmt* is invalid or *data* is the wrong length.
    """
    if not validate_struct_format(fmt):
        raise ValueError(f"Unsafe struct format: {fmt!r}")
    expected = struct.calcsize(fmt)
    if len(data) != expected:
        raise ValueError(f"Expected {expected} bytes for format {fmt!r}, got {len(data)}")
    return struct.unpack(fmt, data)
