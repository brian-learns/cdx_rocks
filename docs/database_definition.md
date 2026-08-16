# `cdx-rocks` database definition

Goal: provide a fast key/value lookup for [CDXj indexes of WARC files](https://specs.webrecorder.net/cdxj/0.1.0/).

A `cdx-rocks` database consists of a directory or tar file containing the following artifacts.

 1. `cdx-rocks.json` file specifying the catalog file, rocks db directory, and [`struct_format`](./struct_format.md).
 2. A catalog file listing all indexed WARC files, one per line
 3. a RocksDB directory
 4. `extent.json` file with the same contents as /extent API endpoint
 5. [`surt_report.json`](./surt_report.md) file with SURT host label-prefix statistics

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
Position of the file in the catalog is packed into the first part of the value struct, followed by byte offset, and then length.

Entries in the catalog file are lexicographically sorted, which naturally arranges the WARCs in chronological order from oldest to newest.

`extent.json` is derived from the catalog file; `"file_extent":` is the nuver of lines, `"file_oldest":` is the first line, and `"file_newest":` is the last line.  The
`cdx_rocks` server does not read this file, it's provided in the database file to make it eaiser to identify what is in the index.


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

## `surt_report.json`

Statistics artifact maintained by the build and update CLIs. It counts every
SURT host label-prefix seen in the CDXJ input (e.g. `com,example)/page` contributes
+1 to `"com"` and +1 to `"com,example"`; dotted-IP hosts count only their full host),
and is the data source for the `/cdx-index/surt` browse endpoint.

Full specification: [`surt_report.md`](./surt_report.md).
