---
title: Cdx Rocks Demo
emoji: 📉
colorFrom: gray
colorTo: indigo
sdk: docker
pinned: false
license: bsd-3-clause
---
# `cdx_rocks`

`/lookup` server component for https://github.com/brian-learns/ccnget

This repo is on github and a hugging face space.

[🤗 Hugging Face Space](https://huggingface.co/spaces/brian-learns/cc-news-cdx-server) | [🐙 github repo](https://github.com/brian-learns/cdx_rocks)

FastAPI server backed by RocksDB for looking up CDX index records from the Common Crawl News dataset.

## Download Data

| URL | Size | Description |
| :--- | :---: | :--- |
| <https://huggingface.co/buckets/brian-learns/cdx-rocks-demo> | 3.69G | For testing |
| <https://huggingface.co/buckets/brian-learns/cdx-rocks-2023-2024> | 18.2G | Current Hugging Face Space database |
| <https://huggingface.co/buckets/brian-learns/cdx-rocks-monthly> | 77.4G | Full database updated monthly |

```
# put a database directory at ./rocksdb_index when using the docker-compose.yml
uvx hf sync hf://buckets/brian-learns/cdx-rocks-demo rocksdb_index
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
- `surt_report.json` — host label-prefix entry counts (feeds `/cdx-index/surt`)

### `cdx-rocks-update`

Add a single CDXJ file to an existing index. Reads the manifest from the
output directory to get the DB path and struct format — no `CDX_ROCKS` needed.

```bash
cdx-rocks-update /path/to/cc-news_2026_09.cdxj.zst \
    --catalog /path/to/updated_all_warc_paths.txt.zst \
    --output-dir /path/to/index
```

Replaces `all_warc_paths.txt.zst` in the output directory with the new catalog
and refreshes `extent.json` and `surt_report.json` (new counts are merged
into the existing report).

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
| `/cdx-index/surt-browse` | GET | Browse the SURT host tree one level at a time |
| `/cdx-index/surt-prefix` | GET | Wildcard scan: captures under a SURT prefix |
| `/health` | GET | Server health check |
| `/` | GET | Interactive home page (SURT tree browse + prefix scan demo) |
| `/terms` | GET | Data usage & disclaimer notice |
| `/docs` | GET | Swagger/OpenAPI documentation |
| `/redoc` | GET | ReDoc documentation |

### Lookup Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | (required) | URL to look up in the archive |
| `exact` | bool | `false` | Exact SURT match vs prefix match |
| `at` | string | `null` | Timestamp to seek from (YYYYMMDDhhmmss) |
| `limit` | int | 10 | Max results (1-100) |

`url` is always parsed as a URL. For literal SURT keys (a host pattern
copied from `/cdx-index/surt-browse`, or a path prefix) use
`/cdx-index/surt-prefix` instead.

### Surt Browse Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | `""` | SURT host pattern to expand (comma-joined labels, e.g. `com` or `com,example`); empty for the root |
| `limit` | int | 50 | Max children returned (1-200); `total_children` reports the true count |
| `offset` | int | `0` | Children to skip before `limit` is applied (0-based) |

Each child key in the response is itself a valid `pattern`, so the tree can be
walked level by level. Children are returned in rank order (count desc, name
asc) and the order is stable for the life of a server run (the index is frozen
until restart). To walk *all* children of a node, follow `next_offset`:
request, then request again with `offset` set to `next_offset`, until it is
`null`. Offsets past the end return `200` with an empty `children` — no 404.

Counts come from `surt_report.json` (indexed entries,
cumulative across build + updates, not unique URLs). Dotted-IP hosts (which
count only their full host) appear as promoted entries at the root level.

### Surt Prefix Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prefix` | string | (required) | SURT prefix to scan. A host pattern (no `)`) such as `com,aa` matches the host and all its subdomains — never sibling hosts like `com,aaa,ace`. A prefix containing `)` such as `com,aaa,ace)/activities` matches that path prefix (wildcard) |
| `limit` | int | 10 | Max results (1-100) |

Wildcard examples: `http://*.com/` → `prefix=com`;
`https://ace.aaa.com/activities*` → `prefix=com,aaa,ace)/activities`.
Results are in key order (SURT, then timestamp); `total_results` is the number
returned, not a true total. Prefixes whose host was never indexed (not in
`surt_report.json`) return an empty result (`total_results: 0`) — no 404.

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
