"""Conftest: isolate cdx_rocks.server imports from real filesystem state."""

import os
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

import zstandard as zstd

_tmpdir = tempfile.mkdtemp(prefix="cdx_rocks_test_")
(Path(_tmpdir) / "rocks").mkdir(parents=True, exist_ok=True)

os.environ["CDX_ROCKS"] = _tmpdir
os.environ["CATALOG_PATH"] = "/dev/null"

# Mock zstandard.open so lifespan startup doesn't try to read a real catalog.
_orig_zstd_open = zstd.open


def _mock_zstd_open(*args, **kwargs):
    return _orig_zstd_open("/dev/null", mode="rt", encoding="utf-8")


zstd.open = _mock_zstd_open  # type: ignore[attr-defined]

# Now the real import
from cdx_rocks import server  # noqa: F401, E402

# Reset app.state so tests can set it cleanly.
if hasattr(server.app.state, "db"):
    del server.app.state.db
if hasattr(server.app.state, "catalog"):
    del server.app.state.catalog

atexit.register(shutil.rmtree, _tmpdir)
