# `cdx_rocks`

`/lookup` server component for https://github.com/brian-learns/ccnget

FastAPI server backed by RocksDB for looking up CDX index records from the Common Crawl News dataset.

## Download Data

```
# small test index that contains http://example.com/ record
uvx hf sync hf://buckets/brian-learns/cdx-rocks-demo rocksdb_index
# full index
https://huggingface.co/buckets/brian-learns/cdx-rocks-monthly
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

Server reads config from `$CDX_ROCKS/cdx-rocks.json` manifest 

### `cdx-rocks-build`

Build a full cdx-rocks index from CDXJ files.

```bash
cdx-rocks-build \
    --cdxj-dir /path/to/cdxj_files \
    --catalog /path/to/all_warc_paths.txt.zst \
    --output-dir /path/to/index \
    --struct-format '!HQI'
```

Writes to the output directory:
- `rocks/` — RocksDB database
- `cdx-rocks.json` — manifest (catalog, db path, struct format)
- `all_warc_paths.txt.zst` — copied catalog
- `extent.json` — static snapshot of file count and date range

### `cdx-rocks-update`

Add a single CDXJ file to an existing index. Reads the manifest from the
output directory to get the DB path and struct format — no `CDX_ROCKS` needed.

```bash
cdx-rocks-update /path/to/cc-news_2026_09.cdxj.zst \
    --catalog /path/to/updated_all_warc_paths.txt.zst \
    --output-dir /path/to/index
```

Replaces `all_warc_paths.txt.zst` in the output directory with the new catalog
and refreshes `extent.json`.

### `cdx-rocks-shadow`

Create a read-only shadow directory for the RocksDB index (useful for read-replica setups).

```bash
cdx-rocks-shadow \
    --rocksdb-dir /path/to/index/rocks \
    --linksdir /path/to/shadow
```

## Configuration

set `CDX_ROCKS` to point to a [cdx-rocks database](https://github.com/brian-learns/cdx_rocks/blob/main/docs/database_definition.md)


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
