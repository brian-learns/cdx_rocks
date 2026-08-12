"""cdx-rocks — RocksDB-powered CDX index server for Common Crawl News."""

__version__ = "0.2.0"

from cdx_rocks.build import build_index, load_catalog
from cdx_rocks.config import (
    load_manifest,
    resolve_catalog_path,
    resolve_rocks_dir,
    resolve_struct_format,
)
from cdx_rocks.index import VALUE_FORMAT, VALUE_SIZE, query_index
from cdx_rocks.schema import safe_pack, safe_unpack, validate_struct_format
from cdx_rocks.shadow import get_rocks_dir, setup_shadow
from cdx_rocks.update import update_index

__all__ = [
    "VALUE_FORMAT",
    "VALUE_SIZE",
    "__version__",
    "build_index",
    "get_rocks_dir",
    "load_catalog",
    "load_manifest",
    "query_index",
    "resolve_catalog_path",
    "resolve_rocks_dir",
    "resolve_struct_format",
    "safe_pack",
    "safe_unpack",
    "setup_shadow",
    "update_index",
    "validate_struct_format",
]
