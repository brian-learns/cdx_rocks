# Running cdx-rocks on a HuggingFace Space

## Overview

When `HUGGING_FACE=1` is set in the environment, `cdx-rocks` automatically syncs its RocksDB
from a [HF Storage Bucket](https://huggingface.co/docs/hub/main/en/storage-buckets) to a local
ephemeral directory and serves the API from there.

No changes to the Dockerfile or CMD are required — the same image works both locally (with a
mounted `CDX_ROCKS` volume) and on HF Spaces.

## How it works

1. Set `HUGGING_FACE=1` in your Space environment variables
2. The Space starts with the standard CMD:
   ```
   fastapi run ./src/cdx_rocks/server.py --host 0.0.0.0 --port 7860
   ```
3. On first import, `cdx_rocks.hf_space.resolve_hf_base_path()` syncs the bucket to `/tmp/cdx-rocks-hf`
4. The manifest (`cdx-rocks.json`) inside the synced directory is loaded automatically
5. The API serves from the local NVMe-backed `/tmp` disk

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HUGGING_FACE` | *(unset)* | Set to `1` to enable HF Space mode |
| `CDX_ROCKS_HF_DIR` | `/tmp/cdx-rocks-hf` | Where the bucket is synced locally |
| `CDX_ROCKS_HF_BUCKET` | `brian-learns/cdx-rocks-demo` | Which HF bucket to sync |
| `HF_HOME` | `/tmp/hf_cache` | Auto-set by the module; HF/xet cache directory |
| `CDX_ROCKS` | *(auto-set)* | If explicitly set, takes priority over HF Space auto-detect |

## Bucket requirements

The bucket must contain a valid `cdx-rocks` database layout:

```
bucket/
├── cdx-rocks.json          # Manifest with catalog, db, struct_format
├── all_warc_paths.txt.zst  # Catalog file (path matches manifest's "catalog" key)
├── extent.json             # Optional extent metadata
└── rocks/                  # RocksDB directory (path matches manifest's "db" key)
    ├── CURRENT
    ├── MANIFEST-*
    ├── OPTIONS-*
    ├── *.sst
    └── ...
```

See [database_definition.md](./database_definition.md) for the full spec.

## Why /tmp?

HF Spaces run as a non-root user with a read-only `/home`. The `/tmp` directory is the
recommended ephemeral storage — it is backed by fast local NVMe and survives within the
container lifecycle.

The module redirects `HF_HOME` to `/tmp/hf_cache` to avoid permission errors from the
xet file download runtime trying to write to `/home/fastapi/.cache/`.

## Performance notes

- The bucket (~4.3GB for the demo) is synced to `/tmp` on first startup. Subsequent
  container restarts check for `rocks/CURRENT` and skip the download if the files exist.
- The sync uses `ignore_existing=True` so unchanged files are not re-downloaded.
- The RocksDB is opened read-only (`AccessType.read_only()`). Since the `/tmp` files are
  writable copies (not a read-only mount), the shadow directory workaround is not needed.
- The sync is cached per-process via `@functools.cache`, so calling `resolve_hf_base_path()`
  multiple times (e.g. from `resolve_rocks_dir()` and `resolve_catalog_path()`) does not
  trigger multiple downloads.
