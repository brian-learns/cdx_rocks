# Common Crawl News Index Gateway

> Version 0.5.0


URL lookup tool for [Common Crawl News Dataset](https://data.commoncrawl.org/crawl-data/CC-NEWS/index.html) indexed in RocksDB with a simple API.

Command line client [`ccnget` on github](https://github.com/brian-learns/ccnget).

This server [`cdx_rocks` on github](https://github.com/brian-learns/cdx_rocks).
v0.2.0 is the version of the server running now.

Built from the [brian-learns/cdx-cc-news Dataset](https://huggingface.co/datasets/brian-learns/cdx-cc-news)

Files retrieved from Common Crawl are subject to [Common Crawl Terms of Use](https://commoncrawl.org/terms-of-use) and the original publisher's copyright.

THIS SOFTWARE IS PROVIDED BY "AS IS" AND ANY EXPRESS OR IMPLIED
WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE OPERATORS OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.



## Path Table

| Method | Path | Description |
| --- | --- | --- |
| GET | [/cdx-index/lookup](#getcdx-indexlookup) | Lookup Endpoint |
| GET | [/cdx-index/extent](#getcdx-indexextent) | Extent Endpoint |

## Reference Table

| Name | Path | Description |
| --- | --- | --- |
| CaptureResult | [#/components/schemas/CaptureResult](#componentsschemascaptureresult) | A single archive capture record returned from the index lookup. |
| ExtentResponse | [#/components/schemas/ExtentResponse](#componentsschemasextentresponse) | Extent of the WARC files in this index |
| HTTPValidationError | [#/components/schemas/HTTPValidationError](#componentsschemashttpvalidationerror) |  |
| LookupResponse | [#/components/schemas/LookupResponse](#componentsschemaslookupresponse) | Response body for a CDX index lookup query. |
| ValidationError | [#/components/schemas/ValidationError](#componentsschemasvalidationerror) |  |

## Path Details

***

### [GET]/cdx-index/lookup

- Summary  
Lookup Endpoint

- Operation id  
lookup_endpoint_cdx_index_lookup_get

- Description  
REST API endpoint supporting exact, partial prefix, or timestamp-targeted matching.

#### Parameters(Query)

```typescript
// URL to look for in the archive
url: string
```

```typescript
// Exact matching vs prefix matching
exact?: boolean
```

```typescript
// Timestamp (YYYYMMDDhhmmss). If exact=True, seeks from timestamp. If exact=False, finds closest match.
at?: Partial(string) & Partial(null)
```

```typescript
// Maximum number of results to return
limit?: integer //default: 10
```

#### Responses

- 200 Successful Response

`application/json`

```typescript
// Response body for a CDX index lookup query.
{
  // Original requested URL
  query_url: string
  // SURT string used for lookup
  surt_prefix: string
  // Whether exact matching was used
  exact_match: boolean
  // Timestamp parameter requested
  at_timestamp?: Partial(string) & Partial(null)
  // Number of results returned
  total_results: integer
  // Maximum results cap requested
  limit: integer
  // A single archive capture record returned from the index lookup.
  results: {
    // SURT-formatted key prefix
    surt_key: string
    // Capture timestamp (YYYYMMDDhhmmss)
    timestamp: string
    // Path to the WARC file in Common Crawl
    warc_path: string
    // Byte offset in the WARC file
    offset: integer
    // Record length in bytes
    length: integer
  }[]
}
```

- 422 Validation Error

`application/json`

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
    ctx: {
    }
  }[]
}
```

***

### [GET]/cdx-index/extent

- Summary  
Extent Endpoint

- Operation id  
extent_endpoint_cdx_index_extent_get

- Description  
show what content is indexed on this server

#### Responses

- 200 Successful Response

`application/json`

```typescript
// Extent of the WARC files in this index
{
  // number of files covered by this index
  file_extent: integer
  // first WARC file in this index
  file_oldest: string
  // last WARC file added to this index
  file_newest: string
}
```

## References

### #/components/schemas/CaptureResult

```typescript
// A single archive capture record returned from the index lookup.
{
  // SURT-formatted key prefix
  surt_key: string
  // Capture timestamp (YYYYMMDDhhmmss)
  timestamp: string
  // Path to the WARC file in Common Crawl
  warc_path: string
  // Byte offset in the WARC file
  offset: integer
  // Record length in bytes
  length: integer
}
```

### #/components/schemas/ExtentResponse

```typescript
// Extent of the WARC files in this index
{
  // number of files covered by this index
  file_extent: integer
  // first WARC file in this index
  file_oldest: string
  // last WARC file added to this index
  file_newest: string
}
```

### #/components/schemas/HTTPValidationError

```typescript
{
  detail: {
    loc?: Partial(string) & Partial(integer)[]
    msg: string
    type: string
    ctx: {
    }
  }[]
}
```

### #/components/schemas/LookupResponse

```typescript
// Response body for a CDX index lookup query.
{
  // Original requested URL
  query_url: string
  // SURT string used for lookup
  surt_prefix: string
  // Whether exact matching was used
  exact_match: boolean
  // Timestamp parameter requested
  at_timestamp?: Partial(string) & Partial(null)
  // Number of results returned
  total_results: integer
  // Maximum results cap requested
  limit: integer
  // A single archive capture record returned from the index lookup.
  results: {
    // SURT-formatted key prefix
    surt_key: string
    // Capture timestamp (YYYYMMDDhhmmss)
    timestamp: string
    // Path to the WARC file in Common Crawl
    warc_path: string
    // Byte offset in the WARC file
    offset: integer
    // Record length in bytes
    length: integer
  }[]
}
```

### #/components/schemas/ValidationError

```typescript
{
  loc?: Partial(string) & Partial(integer)[]
  msg: string
  type: string
  ctx: {
  }
}
```