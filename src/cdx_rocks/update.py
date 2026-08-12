"""Update an existing cdx-rocks index with a new CDXJ file.

Adds records from a single CDXJ file into an existing RocksDB database,
replaces the catalog, and refreshes extent.json.

Usage
-----
    cdx-rocks-update /path/to/cc-news_2026_09.cdxj.zst \
        --catalog /path/to/updated_all_warc_paths.txt.zst \
        --output-dir /path/to/index
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import zstandard as zstd
from rocksdict import DBCompactionStyle, DBCompressionType, Options, Rdict, WriteBatch

from cdx_rocks.config import ManifestError, load_manifest
from cdx_rocks.schema import safe_pack, validate_struct_format

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

BATCH_SIZE = 100_000


def load_catalog(catalog_path: str) -> dict[str, int]:
    """Load the WARC catalog and return {filename: 1-indexed ID}."""
    name_to_id: dict[str, int] = {}
    dctx = zstd.ZstdDecompressor()

    logger.info("Loading catalog from %s ...", catalog_path)
    with open(catalog_path, "rb") as fh:
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for global_id, line in enumerate(text_stream, start=1):
                full_path = line.strip()
                if not full_path:
                    continue
                filename = os.path.basename(full_path)
                name_to_id[filename] = global_id

    logger.info("Catalog loaded: %d entries.", len(name_to_id))
    return name_to_id


def _write_extent(catalog_path: str, output_dir: Path) -> None:
    """Write extent.json from the catalog file into output_dir."""
    dctx = zstd.ZstdDecompressor()
    first_path: str | None = None
    last_path: str | None = None
    count = 0

    with open(catalog_path, "rb") as fh:
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for line in text_stream:
                stripped = line.strip()
                if not stripped:
                    continue
                count += 1
                if first_path is None:
                    first_path = stripped
                last_path = stripped

    extent = {
        "file_extent": count,
        "file_oldest": first_path or "",
        "file_newest": last_path or "",
    }

    extent_path = output_dir / "extent.json"
    extent_path.write_text(json.dumps(extent, indent=2) + "\n")
    logger.info("Wrote %s (%d files).", extent_path, count)


def update_index(
    cdxj_file: str,
    catalog_path: str,
    output_dir: str,
) -> None:
    """Add records from *cdxj_file* into the existing index at *output_dir*.

    Reads the manifest from *output_dir* to get the DB path and struct format.
    Copies the updated catalog into *output_dir* and refreshes extent.json.
    """
    out = Path(output_dir)

    # Load manifest to get DB directory and struct format
    manifest_path = out / "cdx-rocks.json"
    if not manifest_path.is_file():
        raise ManifestError(
            f"No cdx-rocks.json manifest found in {output_dir}. Run cdx-rocks-build first to create the initial index."
        )

    cfg = load_manifest(manifest_path)
    db_dir = Path(cfg["db"])
    struct_format = cfg["struct_format"]

    # Validate struct format
    if not validate_struct_format(struct_format):
        raise ValueError(f"Invalid struct format in manifest: {struct_format!r}")

    logger.info("Struct format: %s", struct_format)
    logger.info("DB directory: %s", db_dir)

    name_to_id = load_catalog(catalog_path)

    opts = Options(raw_mode=True)
    opts.set_compression_type(DBCompressionType.zstd())
    opts.set_compaction_style(DBCompactionStyle.universal())
    opts.set_write_buffer_size(512 * 1024 * 1024)
    opts.set_max_write_buffer_number(6)

    logger.info("Opening RocksDB at %s", db_dir)
    db = Rdict(str(db_dir), options=opts)

    dctx = zstd.ZstdDecompressor()
    record_count = 0

    logger.info("Processing %s ...", cdxj_file)
    batch = WriteBatch(raw_mode=True)
    last_key: bytes | None = None

    with open(cdxj_file, "rb") as fh:
        with dctx.stream_reader(fh, read_size=4 * 1024 * 1024) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for line in text_stream:
                if not line.strip() or line.startswith("!"):
                    continue

                parts = line.split(" ", 2)
                if len(parts) < 3:
                    continue

                surt_url = parts[0]
                timestamp = parts[1]
                compound_key = f"{surt_url}\x00{timestamp}".encode("utf-8")

                if compound_key == last_key:
                    continue

                try:
                    record = json.loads(parts[2])
                    filename = record["filename"]
                    if filename not in name_to_id:
                        continue

                    warc_id = name_to_id[filename]
                    offset = int(record["offset"])
                    length = int(record["length"])

                    packed = safe_pack(struct_format, warc_id, offset, length)
                    batch.put(compound_key, packed)
                    last_key = compound_key
                    record_count += 1

                    if record_count % BATCH_SIZE == 0:
                        db.write(batch)
                        batch = WriteBatch(raw_mode=True)
                        logger.info("Progress: %d records ...", record_count)
                except Exception as e:
                    logger.exception("An unexpected error occurred: %s", e)
                    continue

    if record_count > 0:
        db.write(batch)
        logger.info("Update complete: %d records added.", record_count)
    else:
        logger.info("No new records added.")

    db.close()

    # Copy the updated catalog into output_dir
    catalog_dest = out / "all_warc_paths.txt.zst"
    shutil.copy2(catalog_path, str(catalog_dest))
    logger.info("Copied catalog to %s", catalog_dest)

    # Write extent.json from the new catalog
    _write_extent(str(catalog_dest), out)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for cdx-rocks-update."""
    parser = argparse.ArgumentParser(description="Add a CDXJ file to an existing cdx-rocks index.")
    parser.add_argument(
        "cdxj_file",
        help="Path to a .cdxj.zst file",
    )
    parser.add_argument(
        "--catalog",
        required=True,
        help="Path to the updated all_warc_paths.txt.zst (includes new month's WARC files)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Path to the existing index directory (contains cdx-rocks.json, rocks/, etc.)",
    )

    args = parser.parse_args(argv)
    if not Path(args.cdxj_file).exists():
        logger.error("Input file %s not found.", args.cdxj_file)
        sys.exit(1)

    if not Path(args.catalog).exists():
        logger.error("Catalog file %s not found.", args.catalog)
        sys.exit(1)

    try:
        update_index(args.cdxj_file, args.catalog, args.output_dir)
    except Exception as e:
        logger.error("Update failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
