"""FastAPI server for cdx-rocks CDX index lookup."""

import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal, override

import zstandard as zstd
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from rocksdict import AccessType, DBCompressionType, Options, Rdict

from cdx_rocks.config import resolve_catalog_path, resolve_manifest_path, resolve_rocks_dir, resolve_struct_format
from cdx_rocks.index import query_index
from cdx_rocks.report import REPORT_FILENAME, looks_like_surt, surt_browse
from cdx_rocks.schema import validate_struct_format as _validate_struct_format
from cdx_rocks.shadow import get_rocks_dir

# --- logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
access_logger = logging.getLogger("uvicorn.access")

# --- Storage Paths (manifest-first, env-var fallback) ---
_STRUCT_FORMAT = resolve_struct_format()
if not _validate_struct_format(_STRUCT_FORMAT):
    raise RuntimeError(f"Invalid struct_format from manifest/env: {_STRUCT_FORMAT!r}")

ROCKSDB_DIR = get_rocks_dir(
    resolve_rocks_dir(),
    tempfile.mkdtemp(prefix="cdx_", suffix="_rocks"),
)
CATALOG_PATH = resolve_catalog_path()
# The SURT report lives in the index directory next to the manifest.
# If the index predates the report feature the file is simply missing.
_MANIFEST_PATH = resolve_manifest_path()
SURT_REPORT_PATH = (
    (_MANIFEST_PATH.parent / REPORT_FILENAME) if _MANIFEST_PATH else Path(ROCKSDB_DIR).parent / REPORT_FILENAME
)

API_VERSION = "0.6.0"
DESCRIPTION = f"""
URL lookup tool for [Common Crawl News Dataset](https://data.commoncrawl.org/crawl-data/CC-NEWS/index.html) indexed in RocksDB with a simple API.

Command line client [`ccnget` on github](https://github.com/brian-learns/ccnget).

This server [`cdx_rocks` on github](https://github.com/brian-learns/cdx_rocks).
v{version("cdx_rocks")} is the version of the server running now.

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

    query_url: Annotated[str, Field(description="Original query as requested (URL or literal SURT key)")]
    surt_prefix: Annotated[str, Field(description="SURT string used for lookup")]
    exact_match: Annotated[bool, Field(description="Whether exact matching was used")]
    at_timestamp: Annotated[str | None, Field(description="Timestamp parameter requested")] = None
    total_results: Annotated[int, Field(description="Number of results returned")]
    limit: Annotated[int, Field(description="Maximum results cap requested")]
    results: Annotated[list[CaptureResult], Field(description="List of matched WARC captures")]


class ExtentResponse(BaseModel):
    """Extent of the WARC files in this index"""

    file_extent: Annotated[int, Field(description="number of files covered by this index")]
    file_oldest: Annotated[str, Field(description="first WARC file in this index")]
    file_newest: Annotated[str, Field(description="last WARC file added to this index")]


class SurtBrowseResponse(BaseModel):
    """One hop down the SURT host tree from ``/cdx-index/surt``.

    Children are keyed by full pattern string (e.g. ``"com,example"``), so
    the value is also the URL to fetch the next level.
    """

    pattern: Annotated[str, Field(description="Pattern browsed ('' is the root)")]
    count: Annotated[int, Field(description="Indexed entries under this exact host pattern")]
    total_entries: Annotated[int, Field(description="Total entries in the whole index")]
    children: Annotated[
        dict[str, int],
        Field(description="Direct children (pattern -> count), sorted by count desc, capped by limit"),
    ]
    total_children: Annotated[int, Field(description="Number of children before the limit was applied")]


class HealthCheckFilter(logging.Filter):
    """Drop access-log records for /health so Docker healthcheck pings don't flood stdout."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        # Check the fully formatted log message for /health
        if "/health" in record.getMessage():
            return False
        return True


access_logger.addFilter(HealthCheckFilter())


# --- FastAPI Startup/Shutdown Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI startup/shutdown manager: loads the WARC catalog and mounts the RocksDB index."""
    logger.info("Loading global WARC path catalog into memory...")
    catalog: dict[int, str] = {}
    with zstd.open(CATALOG_PATH, mode="rt", encoding="utf-8") as text_stream:
        for global_id, line in enumerate(text_stream, start=1):
            full_path = line.strip()
            if full_path:
                catalog[global_id] = full_path

    logger.info(f"Catalog loaded ({len(catalog):,} paths).")
    app.state.catalog = catalog

    opts = Options(raw_mode=True)
    opts.set_compression_type(DBCompressionType.zstd())

    dir_path = Path(ROCKSDB_DIR)
    file_count = sum(1 for x in dir_path.iterdir() if x.is_file())
    logger.info(f"RocksDB directory: {ROCKSDB_DIR} ({file_count} files)")

    logger.info("Opening RocksDB index...")
    db = Rdict(ROCKSDB_DIR, options=opts, access_type=AccessType.read_only())
    app.state.db = db
    logger.info("Database opened successfully.")

    yield

    db.close()


app = FastAPI(title="Common Crawl News Index Gateway", lifespan=lifespan, description=DESCRIPTION, version=API_VERSION)

api_router = APIRouter(prefix="/cdx-index")


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect the root URL to the Swagger/OpenAPI docs page."""
    return RedirectResponse(url="/docs")


@app.get("/lookup", include_in_schema=False)
def redirect_old_lookup(request: Request):
    """Redirect /lookup to /cdx-index/lookup"""
    # 307 Redirect preserves the request method (GET, POST, etc.)
    return RedirectResponse(url=f"/cdx-index/lookup?{request.url.query}")


@app.get("/extent", include_in_schema=False)
def redirect_old_extent():
    """Redirect /extent to /cdx-index/extent"""
    return RedirectResponse(url="/cdx-index/extent")


@app.get("/surt", include_in_schema=False)
def redirect_surt(request: Request):
    """Redirect /surt to /cdx-index/surt"""
    return RedirectResponse(url=f"/cdx-index/surt?{request.url.query}")


@app.get("/health", include_in_schema=False)
async def health():
    """Healthcheck endpoint. Verifies catalog and RocksDB are loaded."""
    db = getattr(app.state, "db", None)
    catalog = getattr(app.state, "catalog", None)

    if db is None or catalog is None:
        raise HTTPException(status_code=503, detail="Index not ready.")

    return {"status": "ok"}


# --- FastAPI Route ---
@api_router.get("/lookup", response_model=LookupResponse)
async def lookup_endpoint(
    url: Annotated[str, Query(description="URL to look for in the archive, or a literal SURT key (see key)")],
    key: Annotated[
        Literal["url", "surt"],
        Query(
            description=(
                "How to read the url parameter. 'url' (default): parse as a URL — unless it "
                "already looks like a SURT key (has commas and no scheme), in which case it is "
                "used verbatim. 'surt': always treat url as a literal SURT key."
            )
        ),
    ] = "url",
    exact: Annotated[bool, Query(description="Exact matching vs prefix matching")] = False,
    at: Annotated[
        str | None,
        Query(
            description="Timestamp (YYYYMMDDhhmmss). If exact=True, seeks from timestamp. If exact=False, finds closest match."
        ),
    ] = None,
    limit: Annotated[int, Query(description="Maximum number of results to return", ge=1, le=100)] = 10,
):
    """REST API endpoint supporting exact, partial prefix, or timestamp-targeted matching.

    Accepts URLs (``http://www.yahoo.com/``) or literal SURT keys
    (``com,yahoo,news`` — e.g. copied from ``/cdx-index/surt``). SURT-looking
    input (commas, no scheme) is auto-detected; force it with ``key=surt``.
    """
    as_surt_key = key == "surt" or looks_like_surt(url)
    try:
        surt_prefix, captures = query_index(
            app, url, exact_match=exact, limit=limit, at=at, surt_key=url if as_surt_key else None
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed URL payload: {e!s}") from e

    return {
        "query_url": url,
        "surt_prefix": surt_prefix,
        "exact_match": exact,
        "at_timestamp": at,
        "total_results": len(captures),
        "limit": limit,
        "results": captures,
    }


@api_router.get("/extent", response_model=ExtentResponse)
async def extent_endpoint():
    """show what content is indexed on this server"""
    catalog: dict[int, str] = getattr(app.state, "catalog", {})
    if not catalog:
        raise HTTPException(status_code=500, detail="Catalog not loaded.")

    first_key = min(catalog)
    last_key = max(catalog)
    return {
        "file_extent": len(catalog),
        "file_oldest": catalog[first_key],
        "file_newest": catalog[last_key],
    }


def _load_surt_report() -> dict[str, object] | None:
    """Read surt_report.json from the index directory, or None if absent/corrupt."""
    try:
        data = json.loads(SURT_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@api_router.get("/surt", response_model=SurtBrowseResponse)
async def surt_browse_endpoint(
    pattern: Annotated[
        str,
        Query(
            description=(
                "SURT host pattern to expand (comma-joined labels, e.g. 'com' or 'com,example'). "
                "Empty for the root level."
            )
        ),
    ] = "",
    limit: Annotated[int, Query(description="Maximum number of children to return", ge=1, le=200)] = 50,
):
    """Browse the index's SURT host tree one level at a time.

    Each child key is itself a valid ``pattern`` value, so the tree can be
    walked level by level until a leaf host. Counts are entry totals from
    ``surt_report.json`` (build + updates), not unique URLs.
    """
    report = _load_surt_report()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No surt_report.json in the index directory (index built before the SURT report feature).",
        )

    result = surt_browse(pattern, report, limit=limit)
    return {
        "pattern": result["pattern"],
        "count": result["count"],
        "total_entries": report.get("total_entries", 0),
        "children": result["children"],
        "total_children": result["total_children"],
    }


app.include_router(api_router)


def main_serve() -> None:
    """Entry point for the cdx-rocks-serve CLI command."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(
        description="Start the cdx-rocks CDX index lookup server.",
        epilog="Set CDX_ROCKS=/path/to/index to point to your cdx-rocks.json manifest.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Bind port (default: 7860)",
    )

    args = parser.parse_args()
    uvicorn.run("cdx_rocks.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main_serve()
