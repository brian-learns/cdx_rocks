return to [`cdx-rocks` database definition](./database_definition.md)

# `surt_report.json`

Optional artifact: statistics over the SURT host labels of every indexed entry.
It powers the [`/cdx-index/surt`](../README.md#api-endpoints) browse endpoint, which lets
clients explore the index's host tree one label at a time.

`cdx-rocks-build` writes it fresh; `cdx-rocks-update` merges new counts into the
existing file. Databases built before this artifact existed simply lack it —
consumers must treat it as optional (the server returns 404 from `/cdx-index/surt`).

## Format

A JSON object with two keys:

```json
{
  "total_entries": 6,
  "patterns": {
    "com": 4,
    "com,example": 3,
    "82,2,237,15": 1,
    "com,other": 1,
    "org": 1,
    "org,other": 1
  }
}
```

| Key             | Type   | Meaning                                                            |
|-----------------|--------|--------------------------------------------------------------------|
| `total_entries` | int    | Number of CDXJ entries counted (one per record written to the DB)  |
| `patterns`      | object | Map of SURT host label-prefix → entry count, sorted (see below)     |

The example above is what the builder emits for these six synthetic entries:

```
com,example)/a
com,example)/b
com,other)/x
org,other)/y
82,2,237,15)/p
com,example)/c
```

## Pattern semantics

For each indexed entry, take its SURT key (e.g. `com,example)/page`). The **host**
is everything before the first `)` — `com,example` (a bare host has no `)` at all).
The host's labels are split on `,` and counted **cumulatively left to right**, so
the entry contributes:

```
+1 to "com"
+1 to "com,example"
```

A host with three labels (e.g. `uk,co,dailymail`) contributes to all three prefixes.

**Numeric hosts are the exception.** Hosts made entirely of numeric labels — the
SURT form of dotted IP addresses, such as `82,2,237,15)` — contribute only to the
full host string, never to sub-prefixes. This keeps the tree honest (there is no
meaningful "sub-domain" relationship between IP octets) and prevents a handful of
digits from dominating the root level.

Consequences:

- `total_entries` counts entries; a single entry with an *n*-label host increments
  *n* pattern counters (or 1 for a fully numeric host). The sum of all pattern
  counts is therefore larger than `total_entries`.
- A pattern's count is always ≥ the sum of its children's counts, because an entry
  under `com,example,x` also counts toward `com,example`.

## Ordering

`patterns` is serialized sorted by **count descending**, with ties broken
**alphabetically** (plain string sort, so digits precede letters). Consumers must
not rely on key order for correctness, but it makes the file human-readable:
the most common hosts come first.

## Lifecycle and counting guarantees

- **Build** — the report is written fresh from the CDXJ input; it reflects exactly
  the entries written during that build.
- **Update** — the existing report is loaded and the new file's counts are merged
  into it (counts added, not replaced). Counts therefore accumulate across the
  build and every subsequent update.
- **No deduplication** — RocksDB dedupes exact key collisions (`surt\x00timestamp`),
  but the report does not. Re-processing a CDXJ file that overlaps existing data
  double-counts. Treat the report as a volume statistic, not a cardinality.
- **Tolerance** — readers should tolerate a missing `total_entries` or `patterns`
  (default empty/zero) and should discard missing or corrupt files rather than fail;
  the index itself remains fully usable without the report.

## Consumers

The server's `/cdx-index/surt?pattern=<p>&limit=<n>` endpoint returns one hop of the
tree: `p`'s own count plus its direct children (keys of the form `p,label`), capped
by `limit`. Each child key is itself a valid `pattern`, so the tree is walked level
by level until a leaf host. Host prefixes can then be fed straight back into
`/cdx-index/lookup?url=<pattern>` to retrieve the actual WARC captures.

One quirk: fully numeric hosts have no parent in the report (see above), so the
browse endpoint promotes them to the root level — their entries remain reachable
even though `rsplit(',', 1)[0]` of the pattern is absent from `patterns`.

## Reference implementation

See `cdx_rocks/report.py`: `surt_host_patterns()` (per-entry expansion),
`ReportCounter` (record/merge/serialize), `load_report()` / `write_report()`
(file I/O), and `surt_browse()` (one hop of tree traversal).
