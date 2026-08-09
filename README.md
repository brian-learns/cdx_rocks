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
# get on the running instance
docker compose exec web /bin/sh
```

## Local Setup

set these environmental variables
 * `ROCKS_READONLY` path to a readonly files
 * `ROCKS_SHADOW` path to fake rocksdb that rockdict will use
 * `CATALOG_PATH` path to the master list of WARC files

So, [RocksDB](https://rocksdb.org/) is something that Facebook created for fast key/value lookup that can use bloom filters.

[`rocksdict`](https://rocksdict.github.io/RocksDict/rocksdict.html) is a python library that has the best current support for RocksDB, other options require on to compile RocksDB from source, but `rocksdict` just installes with `uv`.

RocksDB has a readonly mode, but `rocksdict` seems to insist in writing a `rocksdict-config.json` into the data directory.

`setup_shadow(rocksdb_dir: Path, linksdir: Path) -> Path` or the command `uv run cdx-rocks "$ROCKS_READONLY" "$ROCKS_SHADOW"` will process a RockDB data directory
into a new directory with symbolic links to the read only files.  `rocksdict-config.json` is then copied to the shadow directory.  This lets the FastAPI start 
when the data is read-only or has other permissions challanges.

## tests

```bash
make test
```

load test
```bash
uv run locust -f tests/locustfile.py
```
