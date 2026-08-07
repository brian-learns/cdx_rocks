# `cdx_rocks`

`/lookup` server component for https://github.com/brian-learns/ccnget

## Download Data
downloads over 75G of rocksdb index files and master catalog file of warc paths.
```bash
make loaddata
````

## Run the server
```bash
docker compose up
# or on macOS
container-compose up
# change the port
CDX_PORT=8000 docker compose up
# rebuild
docker compose up --build
```

## Local Setup
set these environmental variables
 * `ROCKS_READONLY` path to a readonly files
 * `ROCKS_SHADOW` path to fake rocksdb that rockdict will use
 * `CATALOG_PATH` path to the master list of WARC files

```bash
uv run cdx-rocks "$ROCKS_READONLY" "$ROCKS_SHADOW"
```

## tests

```bash
make test
```
