"""Configuration via cdx-rocks.json manifest.

The only environment variable is ``CDX_ROCKS``, which must point to a directory
containing ``cdx-rocks.json`` (or directly to the JSON file).

Manifest format (JSON array):

    ["cdx-rocks", {
        "catalog": "all_warc_paths.txt.zst",
        "db": "rocks/",
        "struct_format": "!HQI"
    }]

All three fields are required. If the manifest is missing or malformed,
the server refuses to start with a clear error.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from cdx_rocks.hf_space import resolve_hf_base_path
from cdx_rocks.schema import validate_struct_format

# --- logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


class ManifestError(RuntimeError):
    """Raised when the manifest is missing, empty, or malformed."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Read and validate a ``cdx-rocks.json`` manifest file.

    Returns the inner dict with keys ``catalog``, ``db``, and ``struct_format``.

    Raises:
        ManifestError: If the file is missing, empty, or malformed.
    """
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"Manifest not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Top-level must be [identifier, dict]
    if not isinstance(raw, list) or len(raw) != 2:
        raise ManifestError(f"Manifest must be [identifier, config], got {type(raw).__name__} with {len(raw)} elements")

    tag, cfg = raw
    if tag != "cdx-rocks":
        raise ManifestError(f"Expected tag 'cdx-rocks', got {tag!r}")

    if not isinstance(cfg, dict):
        raise ManifestError(f"Config must be a dict, got {type(cfg).__name__}")

    for key in ("catalog", "db", "struct_format"):
        if key not in cfg:
            raise ManifestError(f"Manifest missing required key '{key}'")

    # Validate struct_format
    fmt = cfg["struct_format"]
    if not validate_struct_format(fmt):
        raise ManifestError(f"Invalid struct_format in manifest: {fmt!r}")

    # Resolve relative paths against the manifest's parent directory
    manifest_dir = path.parent
    result = dict(cfg)
    if not Path(result["catalog"]).is_absolute():
        result["catalog"] = str(manifest_dir / result["catalog"])
    if not Path(result["db"]).is_absolute():
        result["db"] = str(manifest_dir / result["db"])

    logger.info("Loaded manifest: %s", result)
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


def resolve_manifest_path(cdx_rocks_env: str | None = None) -> Path | None:
    """Return the path to the ``cdx-rocks.json`` manifest, or ``None``.

    Uses the same resolution chain as the other resolvers (``$CDX_ROCKS``
    first, then the HF Space base path). Returns ``None`` when no manifest
    is available (e.g. the ``/data`` fallback without ``CDX_ROCKS`` set).
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    if not cdx_rocks_env:
        hf_path = resolve_hf_base_path()
        if hf_path is not None:
            cdx_rocks_env = hf_path

    if not cdx_rocks_env:
        return None

    return _find_manifest(cdx_rocks_env)


def resolve_rocks_dir(cdx_rocks_env: str | None = None) -> str:
    """Return the RocksDB directory path from the manifest.

    Requires ``$CDX_ROCKS`` (or explicit argument) pointing to a manifest.
    Falls back to ``/data`` if the env is not set, so the module can be imported
    (e.g. for ``--help``). The server will fail at startup if the manifest is
    missing when it tries to open the DB.
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    # HF Space: sync bucket if needed (cached per-process)
    if not cdx_rocks_env:
        hf_path = resolve_hf_base_path()
        if hf_path is not None:
            cdx_rocks_env = hf_path

    if not cdx_rocks_env:
        return "/data"

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is None:
        raise ManifestError(
            f"No cdx-rocks.json manifest found at {Path(cdx_rocks_env)} or {Path(cdx_rocks_env) / 'cdx-rocks.json'}"
        )

    return load_manifest(manifest)["db"]


def resolve_catalog_path(cdx_rocks_env: str | None = None) -> str:
    """Return the catalog file path from the manifest.

    Requires ``$CDX_ROCKS`` (or explicit argument) pointing to a manifest.
    Falls back to ``/data/all_warc_paths.txt.zst`` if the env is not set, so the
    module can be imported (e.g. for ``--help``). The server will fail at startup
    if the manifest is missing when it tries to open the DB.
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    # HF Space: sync bucket if needed (cached per-process)
    if not cdx_rocks_env:
        hf_path = resolve_hf_base_path()
        if hf_path is not None:
            cdx_rocks_env = hf_path

    if not cdx_rocks_env:
        return "/data/all_warc_paths.txt.zst"

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is None:
        raise ManifestError(
            f"No cdx-rocks.json manifest found at {Path(cdx_rocks_env)} or {Path(cdx_rocks_env) / 'cdx-rocks.json'}"
        )

    return load_manifest(manifest)["catalog"]


def resolve_struct_format(cdx_rocks_env: str | None = None) -> str:
    """Return the struct format string from the manifest.

    Requires ``$CDX_ROCKS`` (or explicit argument) pointing to a manifest.
    Falls back to ``!HQI`` if the env is not set, so the module can be imported
    (e.g. for ``--help``). The server will fail at startup if the manifest is
    missing when it tries to open the DB.
    """
    if cdx_rocks_env is None:
        cdx_rocks_env = os.environ.get("CDX_ROCKS")

    # HF Space: sync bucket if needed (cached per-process)
    if not cdx_rocks_env:
        hf_path = resolve_hf_base_path()
        if hf_path is not None:
            cdx_rocks_env = hf_path

    if not cdx_rocks_env:
        return "!HQI"

    manifest = _find_manifest(cdx_rocks_env)
    if manifest is None:
        raise ManifestError(
            f"No cdx-rocks.json manifest found at {Path(cdx_rocks_env)} or {Path(cdx_rocks_env) / 'cdx-rocks.json'}"
        )

    return load_manifest(manifest)["struct_format"]
