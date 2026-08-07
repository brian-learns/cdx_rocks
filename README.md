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
```

