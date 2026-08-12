"""Build a cdx-rocks index from CDXJ files.

Reads CDXJ index files (zstd-compressed), resolves WARC filenames to catalog
IDs, and writes a RocksDB database with the cdx-rocks key/value layout.

Usage
-----
    cdx-rocks-build --cdxj-dir /path/to/cdxj --catalog all_warc_paths.txt.zst --output-dir /path/to/index

The builder writes ``cdx-rocks.json`` manifest alongside the catalog and db
directory on completion.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from pathlib import Path

import zstandard as zstd
from rocksdict import DBCompactionStyle, DBCompressionType, Options, Rdict, WriteBatch

from cdx_rocks.schema import safe_pack, validate_struct_format

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

DEFAULT_STRUCT_FORMAT = "!HQI"
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


def build_index(
    cdxj_dir: str,
    catalog_path: str,
    output_dir: str,
    struct_format: str = DEFAULT_STRUCT_FORMAT,
) -> None:
    """Build a full cdx-rocks index from CDXJ files in *cdxj_dir*.

    Writes the RocksDB database to *output_dir/rocks/*, copies the catalog to
    *output_dir/*, and creates *output_dir/cdx-rocks.json*.
    """
    if not validate_struct_format(struct_format):
        raise ValueError(f"Invalid struct format: {struct_format!r}")

    name_to_id = load_catalog(catalog_path)

    db_dir = Path(output_dir) / "rocks"
    db_dir.mkdir(parents=True, exist_ok=True)

    opts = Options(raw_mode=True)
    opts.set_compression_type(DBCompressionType.zstd())
    opts.set_compaction_style(DBCompactionStyle.universal())
    opts.set_write_buffer_size(512 * 1024 * 1024)
    opts.set_max_write_buffer_number(6)

    logger.info("Opening RocksDB at %s", db_dir)
    db = Rdict(str(db_dir), options=opts)

    dctx = zstd.ZstdDecompressor()
    total_records = 0
    total_dups = 0

    cdxj_files = sorted(f for f in os.listdir(cdxj_dir) if f.endswith(".cdxj.zst"))
    logger.info("Found %d CDXJ files.", len(cdxj_files))

    for cdxj_file in cdxj_files:
        input_path = os.path.join(cdxj_dir, cdxj_file)
        logger.info("Processing %s ...", cdxj_file)

        batch = WriteBatch(raw_mode=True)
        file_records = 0
        last_key: bytes | None = None

        with open(input_path, "rb") as fh:
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
                        total_dups += 1
                        continue

                    try:
                        record = json.loads(parts[2])
                        filename = record["filename"]
                        warc_id = name_to_id[filename]
                        offset = int(record["offset"])
                        length = int(record["length"])

                        packed = safe_pack(struct_format, warc_id, offset, length)
                        batch.put(compound_key, packed)
                        last_key = compound_key
                        file_records += 1
                        total_records += 1

                        if file_records % BATCH_SIZE == 0:
                            db.write(batch)
                            batch = WriteBatch(raw_mode=True)
                    except Exception as e:
                        logger.exception("An unexpected error occurred: %s", e)
                        continue

        db.write(batch)
        logger.info("Finished %s: %d records.", cdxj_file, file_records)

    db.close()

    # Write manifest
    manifest_path = Path(output_dir) / "cdx-rocks.json"
    manifest = [
        "cdx-rocks",
        {
            "catalog": "all_warc_paths.txt.zst",
            "db": "rocks/",
            "struct_format": struct_format,
        },
    ]
    # Copy catalog into output
    import shutil

    shutil.copy2(catalog_path, Path(output_dir) / "all_warc_paths.txt.zst")
    manifest_path.write_text(json.dumps(manifest) + "\n")

    # Write extent.json (static snapshot of the catalog)
    extent = {
        "file_extent": len(name_to_id),
        "file_oldest": catalog_path,
        "file_newest": catalog_path,
    }
    # Load catalog in order to get first/last paths
    catalog_paths: list[str] = []
    with open(catalog_path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for line in text_stream:
                stripped = line.strip()
                if stripped:
                    catalog_paths.append(stripped)
    if catalog_paths:
        extent["file_oldest"] = catalog_paths[0]
        extent["file_newest"] = catalog_paths[-1]
    else:
        extent["file_oldest"] = ""
        extent["file_newest"] = ""

    extent_path = Path(output_dir) / "extent.json"
    extent_path.write_text(json.dumps(extent, indent=2) + "\n")

    logger.info(
        "Index built: %d records, %d duplicates dropped, %d WARC files, manifest at %s, extent at %s",
        total_records,
        total_dups,
        len(catalog_paths),
        manifest_path,
        extent_path,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for cdx-rocks-build."""
    parser = argparse.ArgumentParser(description="Build a cdx-rocks index from CDXJ files.")
    parser.add_argument(
        "--cdxj-dir",
        required=True,
        help="Directory containing .cdxj.zst files",
    )
    parser.add_argument(
        "--catalog",
        required=True,
        help="Path to all_warc_paths.txt.zst",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for the index",
    )
    parser.add_argument(
        "--struct-format",
        default=DEFAULT_STRUCT_FORMAT,
        help=f"Struct format string (default: {DEFAULT_STRUCT_FORMAT})",
    )

    args = parser.parse_args(argv)

    try:
        build_index(args.cdxj_dir, args.catalog, args.output_dir, args.struct_format)
    except Exception as e:
        logger.error("Build failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
