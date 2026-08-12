"""Configuration via cdx-rocks.json manifest with env-var fallbacks.

Manifest format (JSON array):

    ["cdx-rocks", {
        "catalog": "all_warc_paths.txt.zst",
        "db": "rocks/",
        "struct_format": "!HQI"
    }]

The manifest file is searched for at ``$CDX_ROCKS/cdx-rocks.json`` or
``$CDX_ROCKS`` itself if it points directly to the JSON file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from cdx_rocks.catalog import DEFAULT_CATALOG_PATH
from cdx_rocks.schema import validate_struct_format

DEFAULT_STRUCT_FORMAT = "!HQI"

# --- logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Read and validate a ``cdx-rocks.json`` manifest file.

    Returns the inner dict with keys ``catalog``, ``db``, and optionally
    ``struct_format``.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the manifest is malformed or contains invalid values.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Top-level must be [identifier, dict]
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError(f"Manifest must be [identifier, config], got {type(raw).__name__} with {len(raw)} elements")

    tag, cfg = raw
    if tag != "cdx-rocks":
        raise ValueError(f"Expected tag 'cdx-rocks', got {tag!r}")

    if not isinstance(cfg, dict):
        raise ValueError(f"Config must be a dict, got {type(cfg).__name__}")

    if "catalog" not in cfg:
        raise ValueError("Manifest missing required key 'catalog'")
    if "db" not in cfg:
        raise ValueError("Manifest missing required key 'db'")

    # Validate struct_format if present
    if "struct_format" in cfg:
        fmt = cfg["struct_format"]
        if not validate_struct_format(fmt):
            raise ValueError(f"Invalid struct_format in manifest: {fmt!r}")

    # Resolve relative paths against the manifest's parent directory
    manifest_dir = path.parent
    result = dict(cfg)
    if not Path(result["catalog"]).is_absolute():
        result["catalog"] = str(manifest_dir / result["catalog"])
    if not Path(result["db"]).is_absolute():
        result["db"] = str(manifest_dir / result["db"])
    logger.info(result)
    return result


def _find_manifest(cdx_rocks_env: str | None) -> Path | None:
    """Locate a cdx-rocks.json manifest under *cdx_rocks_env*.

    Returns the manifest path, or ``None`` if not found.
    """
    if not cdx_rocks_env:
        return None

    base = Path(cdx_rocks_env)

    # If the env points directly to a JSON file, use it
    if base.is_file() and base.suffix == ".json":
        return base

    # Otherwise look for cdx-rocks.json inside the directory
    candidate = base / "cdx-rocks.json"
    if candidate.is_file():
        return candidate

    return None


def resolve_rocks_dir(cdx_rocks_env: str | None = None) -> str:
    """Return the RocksDB directory path.

    Looks for a manifest under ``$CDX_ROCKS`` first, then falls back to the
    environment variable value directly (the directory itself).
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is not None:
        cfg = load_manifest(manifest)
        return cfg["db"]

    # Fallback: use CDX_ROCKS value as the DB directory
    if cdx_rocks_env:
        return cdx_rocks_env

    return "/data"


def resolve_catalog_path(cdx_rocks_env: str | None = None) -> str:
    """Return the catalog file path.

    Looks for a manifest under ``$CDX_ROCKS`` first, then falls back to
    ``$CATALOG_PATH``, then to the compiled-in default.
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is not None:
        cfg = load_manifest(manifest)
        return cfg["catalog"]

    # Fallback: explicit env var
    catalog_env = os.environ.get("CATALOG_PATH")
    if catalog_env:
        return catalog_env

    # Default
    return DEFAULT_CATALOG_PATH


def resolve_struct_format(cdx_rocks_env: str | None = None) -> str:
    """Return the struct format string.

    Looks for a manifest under ``$CDX_ROCKS`` first, then falls back to the
    default ``!HQI``.
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is not None:
        cfg = load_manifest(manifest)
        return cfg.get("struct_format", DEFAULT_STRUCT_FORMAT)

    return DEFAULT_STRUCT_FORMAT
