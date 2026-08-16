"""CDX index query engine for cdx-rocks."""

import struct
from typing import Any

import surt
from fastapi import FastAPI

from cdx_rocks.config import resolve_struct_format

# --- RocksDB value format (resolved from config) ---
# Each value is a big-endian struct:
#   H (uint16) — WARC file ID (index into the catalog)
#   Q (uint64) — Byte offset within the WARC file
#   I (uint32) — Record length in bytes
# Total: 14 bytes (!HQI)
_VALUE_FORMAT = resolve_struct_format()
VALUE_FORMAT: str = _VALUE_FORMAT
VALUE_SIZE: int = struct.calcsize(VALUE_FORMAT)

# Hard cap on the number of keys a single request may examine. The
# proximity path (at + exact_match=False) must walk the whole prefix range
# to find the closest timestamp; without a cap, a caller choosing a short
# prefix (e.g. a bare TLD via key=surt) could make the server walk millions
# of keys per request.
MAX_SCAN_KEYS = 10_000


def query_index(
    app: FastAPI,
    url: str,
    exact_match: bool = False,
    limit: int = 10,
    at: str | None = None,
    surt_key: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Core lookup engine:

    - exact_match=True + at: Seeks directly in RocksDB to the first record >= 'at' timestamp.
    - exact_match=False + at: Scans prefix entries and returns closest matches sorted by proximity to 'at'
      (among the keys within the scan cap — see MAX_SCAN_KEYS).
    - surt_key: If given, used verbatim as the SURT prefix (no URL parsing), so
      callers can query with a literal SURT key such as ``com,yahoo,news``.
    - Availability: at most MAX_SCAN_KEYS keys are examined per request.
    """
    from contextlib import suppress

    db = getattr(app.state, "db", None)
    if db is None:
        raise ValueError("Database engine is offline.")

    catalog: dict[int, str] = getattr(app.state, "catalog", {})

    if surt_key is not None:
        surt_str: str = surt_key
    else:
        surt_str = str(surt.surt(url))

    # Determine prefix and database seeking key
    if exact_match:
        prefix_bytes = f"{surt_str}\x00".encode("utf-8")
        if at:
            # Timestamp seek: Jump straight to captures at/after the 'at' timestamp
            from_key = f"{surt_str}\x00{at}".encode("utf-8")
        else:
            from_key = prefix_bytes
    else:
        prefix_bytes = surt_str.encode("utf-8")
        from_key = prefix_bytes

    results: list[dict[str, str | int]] = []
    scanned = 0

    for key, value in db.items(from_key=from_key):
        if not isinstance(key, bytes):
            continue

        if not key.startswith(prefix_bytes):
            break

        scanned += 1
        decoded_key = key.decode("utf-8", errors="replace")
        if "\x00" in decoded_key:
            surt_key, timestamp = decoded_key.rsplit("\x00", 1)
        else:
            surt_key, timestamp = decoded_key, ""

        absolute_id, offset, length = struct.unpack(VALUE_FORMAT, value)
        warc_path = catalog.get(absolute_id, "PATH_NOT_FOUND")

        results.append(
            {
                "surt_key": surt_key,
                "timestamp": timestamp,
                "warc_path": warc_path,
                "offset": offset,
                "length": length,
            }
        )

        # Early exit for exact seek or standard non-'at' queries
        if (exact_match or at is None) and len(results) >= limit:
            break

        # Availability cap: never examine more than MAX_SCAN_KEYS keys
        if scanned >= MAX_SCAN_KEYS:
            break

    # For partial prefix match with 'at', calculate distance and sort by closest
    # timestamp (within the scanned range, which is capped at MAX_SCAN_KEYS keys)
    if not exact_match and at and results:
        target_ts = at.ljust(14, "0") if len(at) < 14 else at[:14]

        with suppress(ValueError):
            target_num = int(target_ts)
            results.sort(
                key=lambda r: (
                    abs(int(r["timestamp"]) - target_num)
                    if isinstance(r["timestamp"], str) and r["timestamp"].isdigit()
                    else float("inf")
                )
            )

        results = results[:limit]

    return surt_str, results
