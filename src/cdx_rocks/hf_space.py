"""HuggingFace Space bucket sync for cdx-rocks.

When ``HUGGING_FACE=1`` is set in the environment, this module syncs the
demo RocksDB from a HF Storage Bucket to a local ephemeral directory and
returns the path to use as the ``CDX_ROCKS`` base.

The sync is cached per-process: the first call downloads the bucket;
subsequent calls return the cached path immediately.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Defaults ---
DEFAULT_HF_BUCKET = "brian-learns/cdx-rocks-demo"
DEFAULT_LOCAL_DIR = "/tmp/cdx-rocks-hf"  # noqa: S108  # nosec B108  # HF Spaces: /tmp is ephemeral NVMe disk


@cache
def resolve_hf_base_path() -> str | None:
    """Return the local RocksDB base path if running on a HF Space.

    Checks ``HUGGING_FACE`` env var. If set to ``"1"``, syncs the bucket
    to a local directory (cached per-process) and returns its path.
    Otherwise returns ``None``.

    Returns:
        Absolute path to the synced directory, or ``None`` if not on HF Space.
    """
    if os.environ.get("HUGGING_FACE") != "1":
        return None

    # HF Spaces: /home is read-only, so redirect HF/xet cache to /tmp
    os.environ.setdefault("HF_HOME", "/tmp/hf_cache")  # noqa: S108  # nosec B108

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "HUGGING_FACE=1 but huggingface_hub is not installed. Install it with: pip install huggingface_hub"
        ) from exc

    local_dir = os.environ.get("CDX_ROCKS_HF_DIR", DEFAULT_LOCAL_DIR)
    bucket = os.environ.get("CDX_ROCKS_HF_BUCKET", DEFAULT_HF_BUCKET)
    source = f"hf://buckets/{bucket}/"

    # Check if already synced (skip on process restart / hot-reload)
    current_file = Path(local_dir) / "rocks" / "CURRENT"
    if current_file.is_file():
        logger.info("HF bucket already synced at %s — skipping download", local_dir)
        _set_cdx_rocks_env(local_dir)
        return local_dir

    logger.info("Syncing HF bucket %s to %s ...", bucket, local_dir)
    Path(local_dir).mkdir(parents=True, exist_ok=True)

    api = HfApi()
    api.sync_bucket(
        source=source,
        dest=local_dir,
        ignore_existing=True,
        quiet=False,
    )
    logger.info("HF bucket synced to %s", local_dir)

    _set_cdx_rocks_env(local_dir)
    return local_dir


def _set_cdx_rocks_env(path: str) -> None:
    """Set CDX_ROCKS env var so the config resolution chain picks it up."""
    os.environ["CDX_ROCKS"] = path
