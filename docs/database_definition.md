# `cdx-rocks` database definition

Goal: provide a fast key/value lookup for [CDXj indexes of WARC files](https://specs.webrecorder.net/cdxj/0.1.0/).

A `cdx-rocks` database consists of a directory or tar file containing three primary artifacts.

 1. `cdx-rocks.json` file specifying the catalog file, rocks db directory, and [`struct_format`](./struct_format.md).
 2. A catalog file
 3. a RocksDB directory
 4. optional `extent.json` file with the same contents as /extent API endpoint

## `cdx-rocks.json`
sample file
```bash
❯ cat cdx-rocks.json
["cdx-rocks",{"catalog":"all_warc_paths.txt.zst","db":"rocks/","struct_format":"!IQI"}]
```
an annotated file (not valid)
```json
[
  "cdx-rocks",                              # identifies this as a cdx-rocks database  
  {
    "catalog": "all_warc_paths.txt.zst",    # LC_ALL=C sort'ed list of all WARC files in the database
    "db": "rocks/",                         # rocksdb / rocksdict directory
    "struct_format": "!IQI"                 # format of the value packing struct used in the RocksDB
  }
]
```

## Catalog file
List of all WARC files indexed by the `cdx-rocks` database.

```bash
❯ zstdcat all_warc_paths.txt.zst | head
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160826124520-00000.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160826132734-00001.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160827132735-00002.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160827145159-00003.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160828145159-00004.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160829145200-00005.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160830145200-00006.warc.gz
crawl-data/CC-NEWS/2016/08/CC-NEWS-20160831145200-00007.warc.gz
crawl-data/CC-NEWS/2016/09/CC-NEWS-20160901145200-00008.warc.gz
crawl-data/CC-NEWS/2016/09/CC-NEWS-20160902145200-00009.warc.gz
```
position of the file in the catalog is packed into the first part of the value struct, followed by byte offset, and then length.

## RocksDB directory
A RocksDB directory created with `rocksdict` or containing a `rocksdict-config.json` file.

### Keys

```python
compound_key = f"{surt_url}\x00{timestamp}".encode('utf-8')
```

Values
```python
struct_format = value_from_json
packed_value = struct.pack(struct_format, absolute_warc_id, offset, length)
```
