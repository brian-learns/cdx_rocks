import logging
import os
import struct
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, override

import surt
import zstandard as zstd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from rocksdict import AccessType, DBCompressionType, Options, Rdict

from cdx_rocks import setup_shadow

logger = logging.getLogger("uvicorn.error")

# Suppress /health access log lines
access_logger = logging.getLogger("uvicorn.access")


class HealthCheckFilter(logging.Filter):
    """Drop access-log records for /health so Docker healthcheck pings don't flood stdout."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        # Check the fully formatted log message for /health
        if "/health" in record.getMessage():
            return False
        return True


access_logger.addFilter(HealthCheckFilter())

# --- Storage Paths ---
ROCKS_READONLY = os.getenv("ROCKS_READONLY", "/data")
ROCKS_SHADOW = os.getenv("ROCKS_SHADOW", "/code/rocksdb/")
if not Path(ROCKS_SHADOW).is_dir():
    setup_shadow(Path(ROCKS_READONLY), Path(ROCKS_SHADOW))

CATALOG_PATH = os.getenv("CATALOG_PATH", "/code/all_warc_paths.txt.zst")

ID_TO_PATH = {}
GLOBAL_DB = None

DESCRIPTION = """
URL lookup tool for [Common Crawl News Dataset](https://data.commoncrawl.org/crawl-data/CC-NEWS/index.html) indexed in RocksDB with a simple API.

Command line client [`ccnget` on github](https://github.com/brian-learns/ccnget).

This server [`cdx_rocks` on github](https://github.com/brian-learns/cdx_rocks).

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
"""


# --- Pydantic Schema Definitions ---
class CaptureResult(BaseModel):
    """A single archive capture record returned from the index lookup."""

    surt_key: Annotated[str, Field(description="SURT-formatted key prefix")]
    timestamp: Annotated[str, Field(description="Capture timestamp (YYYYMMDDhhmmss)")]
    warc_path: Annotated[str, Field(description="Path to the WARC file in Common Crawl")]
    offset: Annotated[int, Field(description="Byte offset in the WARC file")]
    length: Annotated[int, Field(description="Record length in bytes")]


class LookupResponse(BaseModel):
    """Response body for a CDX index lookup query."""

    query_url: Annotated[str, Field(description="Original requested URL")]
    surt_prefix: Annotated[str, Field(description="SURT string used for lookup")]
    exact_match: Annotated[bool, Field(description="Whether exact matching was used")]
    at_timestamp: Annotated[str | None, Field(description="Timestamp parameter requested")] = None
    total_results: Annotated[int, Field(description="Number of results returned")]
    limit: Annotated[int, Field(description="Maximum results cap requested")]
    results: Annotated[list[CaptureResult], Field(description="List of matched WARC captures")]


# --- Core Index Query Engine ---
def query_index(url: str, exact_match: bool = False, limit: int = 10, at: str | None = None):
    """Core lookup engine:

    - exact_match=True + at: Seeks directly in RocksDB to the first record >= 'at' timestamp.
    - exact_match=False + at: Scans prefix entries and returns closest matches sorted by proximity to 'at'.
    """
    if GLOBAL_DB is None:
        raise ValueError("Database engine is offline.")

    surt_str = surt.surt(url)

    # Determine prefix and database seeking key
    if exact_match:
        prefix_bytes = f"{surt_str}\x00".encode("utf-8")
        if at:
            # Timestamp seek: Jump straight to captures at/after the 'at' timestamp
            from_key = f"{surt_str}\x00{at}".encode("utf-8")
        else:
            from_key = prefix_bytes
    else:
        prefix_bytes = surt_str.encode("utf-8")
        from_key = prefix_bytes

    results: list[dict[str, str | int]] = []

    for key, value in GLOBAL_DB.items(from_key=from_key):
        if not isinstance(key, bytes):
            continue

        if not key.startswith(prefix_bytes):
            break

        decoded_key = key.decode("utf-8", errors="replace")
        if "\x00" in decoded_key:
            surt_key, timestamp = decoded_key.rsplit("\x00", 1)
        else:
            surt_key, timestamp = decoded_key, ""

        absolute_id, offset, length = struct.unpack("!HQI", value)
        warc_path = ID_TO_PATH.get(absolute_id, "PATH_NOT_FOUND")

        results.append(
            {
                "surt_key": surt_key,
                "timestamp": timestamp,
                "warc_path": warc_path,
                "offset": offset,
                "length": length,
            }
        )

        # Early exit for exact seek or standard non-'at' queries
        if (exact_match or at is None) and len(results) >= limit:
            break

    # For partial prefix match with 'at', calculate distance and sort by closest timestamp
    if not exact_match and at and results:
        target_ts = at.ljust(14, "0") if len(at) < 14 else at[:14]

        with suppress(ValueError):
            target_num = int(target_ts)
            results.sort(
                key=lambda r: (
                    abs(int(r["timestamp"]) - target_num)
                    if isinstance(r["timestamp"], str) and r["timestamp"].isdigit()
                    else float("inf")
                )
            )

        results = results[:limit]

    return surt_str, results


# --- FastAPI Startup/Shutdown Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI startup/shutdown manager: loads the WARC catalog and mounts the RocksDB index."""
    global ID_TO_PATH, GLOBAL_DB

    print("Loading global WARC path catalog into memory...")
    with zstd.open(CATALOG_PATH, mode="rt", encoding="utf-8") as text_stream:
        for global_id, line in enumerate(text_stream, start=1):
            full_path = line.strip()
            if full_path:
                ID_TO_PATH[global_id] = full_path

    print(f"Catalog loaded ({len(ID_TO_PATH):,} paths).")

    opts = Options(raw_mode=True)
    opts.set_compression_type(DBCompressionType.zstd())

    print("Mounting RocksDB Index...")
    GLOBAL_DB = Rdict(ROCKS_SHADOW, options=opts, access_type=AccessType.read_only())

    dir_path = Path(ROCKS_SHADOW)
    file_count = sum(1 for x in dir_path.iterdir() if x.is_file())
    print(f"Files in directory: {file_count}")
    print("Database mounted successfully.")

    yield


app = FastAPI(title="Common Crawl News Index Gateway", lifespan=lifespan, description=DESCRIPTION, version="0.1.2")


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect the root URL to the Swagger/OpenAPI docs page."""
    return RedirectResponse(url="/docs")


@app.get("/health", include_in_schema=False)
async def health():
    """Minimal healthcheck endpoint. Returns 200 when the app is alive."""
    return {"status": "ok"}


# --- FastAPI Route ---
@app.get("/lookup", response_model=LookupResponse)
async def lookup_endpoint(
    url: Annotated[str, Query(description="URL to look for in the archive")],
    exact: Annotated[bool, Query(description="Exact matching vs prefix matching")] = False,
    at: Annotated[
        str | None,
        Query(
            description="Timestamp (YYYYMMDDhhmmss). If exact=True, seeks from timestamp. If exact=False, finds closest match."
        ),
    ] = None,
    limit: Annotated[int, Query(description="Maximum number of results to return", ge=1, le=100)] = 10,
):
    """REST API endpoint supporting exact, partial prefix, or timestamp-targeted matching."""
    try:
        surt_prefix, captures = query_index(url, exact_match=exact, limit=limit, at=at)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed URL payload: {e!s}") from e

    if not captures:
        raise HTTPException(status_code=404, detail="No matching captures found for prefix.")

    return {
        "query_url": url,
        "surt_prefix": surt_prefix,
        "exact_match": exact,
        "at_timestamp": at,
        "total_results": len(captures),
        "limit": limit,
        "results": captures,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=7860)
