# `cdx_rocks`

`/lookup` server component for https://github.com/brian-learns/ccnget

FastAPI server backed by RocksDB for looking up CDX index records from the Common Crawl News dataset.

## Download Data

Downloads over 75G of RocksDB index files and master catalog file of WARC paths.

```bash
make loaddata
```

## Run the server

```bash
docker compose up
# or on macOS
container-compose up
# change the port
CDX_PORT=8000 docker compose up
# rebuild
docker compose up --build
# get on the running instance
docker compose exec web /bin/sh
```

## Local Setup

Set these environment variables (manifest in `cdx-rocks.json` takes priority if present):

| Variable | Description |
|----------|-------------|
| `CDX_ROCKS` | Path to the `cdx-index` database directory |
| `CATALOG_PATH` | Path to the master list of WARC files |

## CLI Commands

Install the package (or use `uv run`):

```bash
cd cdx_rocks
uv sync
```

### `cdx-rocks-serve`

Start the FastAPI lookup server (default: `127.0.0.1:7860`).

```bash
cdx-rocks-serve
```

Server reads config from `$CDX_ROCKS/cdx-rocks.json` manifest (if present), then falls back to environment variables.

### `cdx-rocks-build`

Build a full cdx-rocks index from CDXJ files.

```bash
cdx-rocks-build \
    --cdxj-dir /path/to/cdxj_files \
    --catalog /path/to/all_warc_paths.txt.zst \
    --output-dir /path/to/index \
    --struct-format !HQI
```

Writes to the output directory:
- `rocks/` — RocksDB database
- `cdx-rocks.json` — manifest (catalog, db path, struct format)
- `all_warc_paths.txt.zst` — copied catalog
- `extent.json` — static snapshot of file count and date range

### `cdx-rocks-update`

Add a single CDXJ file to an existing index.

```bash
cdx-rocks-update /path/to/cc-news_2026_08.cdxj.zst \
    --catalog /path/to/all_warc_paths.txt.zst \
    --db-dir /path/to/index/rocks
```

### `cdx-rocks-shadow`

Create a read-only shadow directory for the RocksDB index (useful for read-replica setups).

```bash
cdx-rocks-shadow \
    --rocksdb-dir /path/to/index/rocks \
    --linksdir /path/to/shadow
```

## Configuration

### Manifest (`cdx-rocks.json`)

Place this file inside your `$CDX_ROCKS` directory. It is the single source of truth:

```json
["cdx-rocks", {
    "catalog": "all_warc_paths.txt.zst",
    "db": "rocks/",
    "struct_format": "!HQI"
}]
```

Config resolution order:
1. `cdx-rocks.json` manifest (if `$CDX_ROCKS` points to a directory containing it, or directly to the file)
2. Environment variables (`CDX_ROCKS`, `CATALOG_PATH`)
3. Hardcoded defaults (`/data`, `/code/all_warc_paths.txt.zst`, `!HQI`)

### Struct Format

| Format | ID size | Total | Max WARC files |
|--------|---------|-------|----------------|
| `!HQI` | 2 bytes (uint16) | 14 bytes | 65,535 |
| `!IQI` | 4 bytes (uint32) | 16 bytes | 4,294,967,295 |

Default is `!HQI` (sufficient for ~50K+ WARC files). Use `!IQI` if your catalog exceeds 65,535 entries.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cdx-index/lookup` | GET | Query CDX index for URL captures |
| `/cdx-index/extent` | GET | Show indexed WARC file count and date range |
| `/health` | GET | Server health check |
| `/docs` | GET | Swagger/OpenAPI documentation |

### Lookup Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | (required) | URL to look up in the archive |
| `exact` | bool | `false` | Exact SURT match vs prefix match |
| `at` | string | `null` | Timestamp to seek from (YYYYMMDDhhmmss) |
| `limit` | int | 10 | Max results (1-100) |

## Tests

```bash
make test
# or
cd cdx_rocks && uv run pytest tests/ -v
```

Load test:

```bash
uv run locust -f tests/locustfile.py
```
