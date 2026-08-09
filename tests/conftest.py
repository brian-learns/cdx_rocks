"""Conftest: isolate app/main.py imports from real filesystem state."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import tempfile
import shutil
import atexit

import zstandard as zstd

_tmpdir = tempfile.mkdtemp(prefix="cdx_rocks_test_")
os.environ["CDX_ROCKS"] = _tmpdir
os.environ["CATALOG_PATH"] = "/dev/null"

# Mock zstandard.open so lifespan startup doesn't try to read a real catalog.
_orig_zstd_open = zstd.open


def _mock_zstd_open(*args, **kwargs):
    return _orig_zstd_open("/dev/null", mode="rt", encoding="utf-8")


zstd.open = _mock_zstd_open  # type: ignore[attr-defined]

# Now the real import
from app import main  # noqa: F401, E402

# Reset app.state so tests can set it cleanly.
if hasattr(main.app.state, "db"):
    del main.app.state.db
if hasattr(main.app.state, "catalog"):
    del main.app.state.catalog

atexit.register(shutil.rmtree, _tmpdir)
