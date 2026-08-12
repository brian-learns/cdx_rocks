# cdx-rocks Database Definition Refactor

## Goal

Reorganize the `cdx_rocks` codebase from a mismatched layout (monolithic `app/main.py` + scattered utilities) into a proper `src/` package with the `cdx-rocks.json` database format spec implemented and index builders migrated from one-off scripts.

## What Changed

### Before

```
cdx_rocks/
├── app/main.py                # Monolithic FastAPI server (311 lines)
├── src/cdx_rocks/__init__.py  # Shadow-dir utility + get_rocks_dir()
├── pyproject.toml             # Entry point pointed to shadow CLI
└── tests/                     # Tests importing from app.main

cdx_rocks.wiki/                # GitHub wiki for spec sketches
├── database_definition.md
├── struct_format.md

cdx-cc-news/                   # One-off index builders (hardcoded EC2 paths)
├── rocksdb_from_cdxj.py
└── rocksdb_monthly.py
```

### After

```
cdx_rocks/
├── pyproject.toml             # 4 CLI entry points
├── src/cdx_rocks/
│   ├── __init__.py            # 23 public exports
│   ├── server.py              # FastAPI app, lifespan, routes
│   ├── index.py               # query_index() engine
│   ├── shadow.py              # Read-only shadow dir workaround
│   ├── catalog.py             # DEFAULT_CATALOG_PATH
│   ├── schema.py              # validate_struct_format, safe_pack, safe_unpack
│   ├── config.py              # cdx-rocks.json manifest parser, resolve_*
│   ├── build.py               # Full index builder CLI
│   └── update.py              # Incremental update CLI
├── tests/
│   ├── test_app.py            # 15 server/query tests
│   ├── test_build.py          # 12 builder/catalog tests
│   ├── test_cdx_rocks.py      # 7 shadow tests
│   ├── test_config.py         # 17 manifest/resolver tests
│   ├── test_schema.py         # 28 struct format tests
│   └── conftest.py            # Test fixtures
├── docs/
│   ├── database_definition.md # Moved from cdx_rocks.wiki/
│   └── struct_format.md       # Moved from cdx_rocks.wiki/
└── openapi/                   # OpenAPI spec docs (unchanged)
```

## Phase 1: Extract and Restructure

- Split `app/main.py` into `server.py` (FastAPI app + routes) and `index.py` (query engine)
- Moved shadow-dir code from `__init__.py` into `shadow.py`
- Created minimal `catalog.py` module
- Rewrote `__init__.py` with clean public exports
- Updated `pyproject.toml` entry points (`cdx-rocks-serve`, `cdx-rocks-shadow`)
- Moved wiki specs from `cdx_rocks.wiki/` into `docs/`
- Removed `app/` directory
- Updated all test imports from `app.main` to `cdx_rocks.server` / `cdx_rocks.index`
- Updated Dockerfile CMD to use new module path

## Phase 2: Implement Database Format Spec

- Created `schema.py` — `validate_struct_format()`, `safe_pack()`, `safe_unpack()` (from markdown spec)
- Created `config.py` — `cdx-rocks.json` manifest parser with `load_manifest()`, `resolve_rocks_dir()`, `resolve_catalog_path()`, `resolve_struct_format()`
- Manifest format: `["cdx-rocks", {"catalog": "...", "db": "...", "struct_format": "!HQI"}]`
- Config resolution chain: manifest → env vars → defaults
- Updated `server.py` to import from config/schema modules
- Backward compatible — env vars `CDX_ROCKS` and `CATALOG_PATH` still work
- Added `test_schema.py` (28 tests) and `test_config.py` (17 tests)

## Phase 3: Migrate Index Builders

- Created `build.py` — full index builder from CDXJ files (`cdx-rocks-build` CLI)
  - `load_catalog()` — shared catalog loading
  - `build_index()` — processes all `.cdxj.zst` files, writes RocksDB + manifest
  - Writes `cdx-rocks.json` manifest on completion
- Created `update.py` — incremental update (`cdx-rocks-update` CLI)
  - `update_index()` — adds one CDXJ file to existing index
- Added `cdx-rocks-build` and `cdx-rocks-update` entry points to `pyproject.toml`
- Updated `__init__.py` with build/update exports
- Added `test_build.py` (12 tests)
- Original scripts in `cdx-cc-news/` remain untouched

## CLI Entry Points

| Command | Module | Description |
|---------|--------|-------------|
| `cdx-rocks-serve` | `cdx_rocks.server:main_serve` | Start FastAPI server |
| `cdx-rocks-build` | `cdx_rocks.build:main` | Build index from CDXJ files |
| `cdx-rocks-update` | `cdx_rocks.update:main` | Add a month to existing index |
| `cdx-rocks-shadow` | `cdx_rocks.shadow:main` | Create read-only shadow dir |

## Test Results

79 tests pass across 5 test files (0 failures):
- 15 server/query tests (`test_app.py`)
- 12 builder/catalog tests (`test_build.py`)
- 7 shadow tests (`test_cdx_rocks.py`)
- 17 manifest/resolver tests (`test_config.py`)
- 28 struct format tests (`test_schema.py`)

## Design Decisions

- Kept `!HQI` as default struct format (14 bytes: H=2, Q=8, I=4)
- `cdx_rocks.wiki/` folded into `docs/` (was GitHub wiki sketch)
- `index_month.py` stays in `cdx-cc-news/` (data-generation, not index-building)
- `ccnget` client package unchanged (separate repo, clean already)
- Builder writes `cdx-rocks.json` manifest + copies catalog into output directory
- Config resolution: manifest first, then env vars, then hardcoded defaults

## Bugs Fixed Post-Refactor

- **`resolve_rocks_dir()` returned `None`** — no fallback when no manifest was found; crashed server on startup. Added fallback to `CDX_ROCKS` env var, then `"/data"`.
- **Dead TODO code in `server.py`** — 30 lines of commented-out sections from the refactor plus a manual user-patch that bypassed the config module. Cleaned to use `resolve_rocks_dir()` and `resolve_catalog_path()` properly.
- **`index.py` hardcoded `VALUE_FORMAT = "!HQI"`** — manifest's `struct_format` was validated at startup but never read by the query engine. Now resolved from config at import time.
- **`extent.json` not written by builder** — spec mentioned it (suggested by HuggingFace tester) but builder only wrote the manifest. Now reads catalog for first/last paths and writes `extent.json`.
- **Integration test scope** — `test_build.py` only tested catalog loading and pack/unpack with mocks. Added `test_integration.py` with 5 real-pipeline tests using actual RocksDB, zstd compression, and the FastAPI endpoint.

## Test Results (Final)

84 tests pass across 6 test files (0 failures):
- 15 server/query tests (`test_app.py`)
- 12 builder/catalog tests (`test_build.py`)
- 7 shadow tests (`test_cdx_rocks.py`)
- 17 manifest/resolver tests (`test_config.py`)
- 5 integration tests (`test_integration.py`)
- 28 struct format tests (`test_schema.py`)

## Remaining Work (Polish & Integration)

- **Original `cdx-cc-news/` scripts** — `rocksdb_from_cdxj.py` and `rocksdb_monthly.py` remain untouched (by design) but are now redundant. Decision needed: deprecate, remove, or leave as reference.
- **Docker image** — `docker compose up --build` verified working. Dockerfile CMD updated for new module path.
- **CLI docs** — `README.md` updated with CLI usage, config resolution, manifest format, struct format table, and API endpoint documentation.
- **`!IQI` comparison** — deferred. `!HQI` caps catalog at 65,535 entries; `!IQI` uses 4-byte IDs. User wants to compare empirically later.
- **Structured output** — `query_index()` could accept `struct_format` as a parameter instead of resolving at import time, enabling per-request format negotiation.
