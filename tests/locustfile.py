# ruff: noqa: S311  # load test: fast non-cryptographic RNG by design
"""Locust load test for the cdx-index API.

Covers the URL/SURT lookup endpoint, the hierarchical SURT browse endpoint,
and the legacy top-level redirects.

Usage:
    locust -f tests/locustfile.py --headless -u 10 -r 1 --run-time 30s
    locust -f tests/locustfile.py  # opens web UI at http://localhost:8089

The server must be running with the same index the load test derives its
SURT patterns from (``$CDX_ROCKS`` at locust import time points to the
index whose ``surt_report.json`` is sampled; the report is read-only and is
never written to). Without a resolvable report the /surt and SURT-lookup
tasks degrade to synthetic patterns, which still exercise the endpoints.
"""

import json
import os
import pathlib
import random
from pathlib import Path
from typing import Any

from locust import HttpUser, between, task

BASE_URL = "http://0.0.0.0:7860/cdx-index"
URLS_FILE = pathlib.Path(__file__).parent / "1000urls.txt"

# Load test URLs once at import time
with open(URLS_FILE) as f:
    URLS = [line.strip() for line in f if line.strip()]

# --- SURT patterns for /surt browsing and SURT-key lookups ---


def _resolve_report_path() -> Path | None:
    """Locate ``surt_report.json`` the same way the server does.

    Mirrors the server's resolution chain (``$CDX_ROCKS`` first, then the
    HF Space base path) without importing the full package, so loading this
    file never triggers a bucket sync.
    """
    base = os.environ.get("CDX_ROCKS")
    if not base and os.environ.get("HUGGING_FACE") == "1":
        base = os.environ.get("CDX_ROCKS_HF_DIR")
    if not base:
        return None

    base = Path(base)
    # The env may point at the manifest file itself or at the directory.
    manifest = base if base.is_file() else base / "cdx-rocks.json"
    if not manifest.is_file():
        return None
    # The report lives next to the manifest, in the index directory.
    return manifest.parent / "surt_report.json"


def _load_surt_patterns(report_path: Path | None) -> list[str]:
    """Pull SURT host patterns out of the index's report, for every depth.

    The report lists every label-prefix seen at build/update time, so the
    sampled set spans the whole host tree (top-level labels down to deep
    sub-hosts). Falls back to a small set of synthetic patterns when the
    report is absent (index built before the SURT report feature) so the
    tasks still exercise the endpoints.
    """
    patterns: list[str] = []
    if report_path is not None and report_path.is_file():
        try:
            data: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
            for pattern in data.get("patterns", {}):
                patterns.append(str(pattern))
        except (OSError, ValueError):
            patterns = []
    if not patterns:
        patterns = ["com", "com,example", "com,example,www", "org", "org,wikipedia"]
    return patterns


SURT_REPORT = _resolve_report_path()
SURT_PATTERNS = _load_surt_patterns(SURT_REPORT)

# Multi-label patterns, used to exercise /surt at depth.
SURT_PATTERNS_MULTI = [p for p in SURT_PATTERNS if "," in p]
if not SURT_PATTERNS_MULTI:
    SURT_PATTERNS_MULTI = ["com,example", "org,wikipedia"]


class LookupUser(HttpUser):
    """Simulate a user randomly querying the /lookup endpoint."""

    host = BASE_URL
    wait_time = between(1, 3)

    @task
    def lookup_random_url(self):
        """Pick a random URL from 1000urls.txt and query /lookup."""
        url = random.choice(URLS)
        self.client.get(
            "/lookup",
            name="/lookup",
            params={"url": url},
        )

    @task(1)
    def lookup_exact(self):
        """Query /lookup with exact=True for a random URL."""
        url = random.choice(URLS)
        self.client.get(
            "/lookup",
            name="/lookup (exact)",
            params={"url": url, "exact": True},
        )

    @task(1)
    def lookup_with_limit(self):
        """Query /lookup with a small limit for a random URL."""
        url = random.choice(URLS)
        limit = random.randint(1, 5)
        self.client.get(
            "/lookup",
            name="/lookup (limited)",
            params={"url": url, "limit": limit},
        )

    @task(1)
    def lookup_surt_key(self):
        """Look up a literal SURT key copied from a /surt browse response.

        key=surt makes the server use the key verbatim (no URL parsing),
        including single-label hosts that would otherwise parse as URLs.
        """
        pattern = random.choice(SURT_PATTERNS)
        self.client.get(
            "/lookup",
            name="/lookup (surt)",
            params={"url": pattern, "key": "surt", "limit": random.randint(1, 10)},
        )


class SurtBrowseUser(HttpUser):
    """Simulate a user walking the SURT host tree one level at a time."""

    host = BASE_URL
    wait_time = between(1, 3)

    @task
    def surt_browse_root(self):
        """List the top-level host labels (root of the tree)."""
        self.client.get(
            "/surt",
            name="/surt (root)",
            params={"limit": random.randint(10, 200)},
        )

    @task(2)
    def surt_browse_one_level(self):
        """Expand a single-label pattern one level down."""
        pattern = random.choice(SURT_PATTERNS)
        if "," in pattern:
            pattern = pattern.split(",")[0]
        self.client.get(
            "/surt",
            name="/surt (level 1)",
            params={"pattern": pattern, "limit": random.randint(10, 200)},
        )

    @task(2)
    def surt_browse_deep(self):
        """Expand a deep (multi-label) pattern to its children."""
        pattern = random.choice(SURT_PATTERNS_MULTI)
        self.client.get(
            "/surt",
            name="/surt (deep)",
            params={"pattern": pattern, "limit": random.randint(10, 200)},
        )

    @task(1)
    def surt_browse_legacy_redirect(self):
        """Follow the top-level /surt redirect to /cdx-index/surt."""
        self.client.get(
            "/surt",
            name="/surt (redirect)",
            params={"pattern": random.choice(SURT_PATTERNS)},
        )

    @task
    def surt_browse_paged(self):
        """Page through root children with offset pagination."""
        first = self.client.get("/surt", name="/surt (page 1)", params={"limit": 50, "offset": 0})
        if first.status_code != 200:
            return
        next_offset = first.json().get("next_offset")
        if next_offset is not None:
            self.client.get("/surt", name="/surt (page 2)", params={"limit": 50, "offset": next_offset})
