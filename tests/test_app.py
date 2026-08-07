"""Tests for app/main.py — query_index() and FastAPI /lookup endpoint."""

import struct
from unittest.mock import MagicMock, patch

import pytest
import surt
from fastapi.testclient import TestClient

# app.main is already imported by conftest.py so GLOBAL_DB / ID_TO_PATH
# live in the same namespace as our patches.
from app import main  # noqa: F401


class MockRdict:
    """Minimal RocksDB stand-in that yields key/value pairs."""

    def __init__(self, items: dict[bytes, bytes]) -> None:
        self._items = dict(sorted(items.items()))

    def items(self, from_key: bytes | None = None) -> list[tuple[bytes, bytes]]:
        if from_key is None:
            return list(self._items.items())
        return [(k, v) for k, v in self._items.items() if k >= from_key]


def _make_key(url: str, ts: str) -> bytes:
    """Build a DB key: surt(url) + NUL + timestamp."""
    return f"{surt.surt(url)}\x00{ts}".encode()


def _make_value(warc_id: int, offset: int, length: int) -> bytes:
    """Pack a value: H (warc_id) + Q (offset) + Q (length)."""
    return struct.pack("!HQI", warc_id, offset, length)


@pytest.fixture()
def db_and_catalog(tmp_path) -> tuple[MockRdict, dict[int, str]]:
    """Seed a mock DB with one WARC entry."""
    catalog = {1: "/crawl-data/warc/2026/12/example.warc.gz"}
    db_items: dict[bytes, bytes] = {
        _make_key("https://example.com/page", "20260801120000"): _make_value(1, 0, 500),
        _make_key("https://example.com/page", "20260802130000"): _make_value(1, 500, 600),
        # Different domain
        _make_key("https://other.org/home", "20260801000000"): _make_value(1, 1800, 100),
    }
    return MockRdict(db_items), catalog


def test_query_index_exact_match(db_and_catalog):
    """Exact match returns all captures for the URL, limited by limit."""
    mock_db, catalog = db_and_catalog
    with patch("app.main.GLOBAL_DB", mock_db), patch("app.main.ID_TO_PATH", catalog):
        surt_prefix, results = main.query_index("https://example.com/page", exact_match=True)
        assert surt_prefix == "com,example)/page"
        assert len(results) == 2  # default limit is 10, we have 2 entries for this URL
        assert results[0]["timestamp"] == "20260801120000"
        assert results[0]["warc_path"] == "/crawl-data/warc/2026/12/example.warc.gz"
        assert results[0]["offset"] == 0
        assert results[0]["length"] == 500


def test_query_index_limit(db_and_catalog):
    """Limit parameter caps results."""
    mock_db, catalog = db_and_catalog
    with patch("app.main.GLOBAL_DB", mock_db), patch("app.main.ID_TO_PATH", catalog):
        _surt_prefix, results = main.query_index("https://example.com/page", exact_match=True, limit=2)
        assert len(results) == 2


def test_query_index_at_timestamp_seek(db_and_catalog):
    """at= with exact_match=True seeks from the given timestamp."""
    mock_db, catalog = db_and_catalog
    with patch("app.main.GLOBAL_DB", mock_db), patch("app.main.ID_TO_PATH", catalog):
        _surt_prefix, results = main.query_index(
            "https://example.com/page", exact_match=True, at="20260802000000"
        )
        # Should only return entries >= 20260802000000
        assert len(results) == 1
        assert results[0]["timestamp"] == "20260802130000"


def test_query_index_prefix_match(db_and_catalog):
    """exact_match=False uses SURT prefix — partial domain match."""
    mock_db, catalog = db_and_catalog
    with patch("app.main.GLOBAL_DB", mock_db), patch("app.main.ID_TO_PATH", catalog):
        _surt_prefix, results = main.query_index("https://example.com", exact_match=False)
        # Prefix "com,example)" matches all entries for example.com
        assert len(results) == 2


def test_query_index_not_found(db_and_catalog):
    """No matching keys returns empty results list."""
    mock_db, catalog = db_and_catalog
    with patch("app.main.GLOBAL_DB", mock_db), patch("app.main.ID_TO_PATH", catalog):
        _surt_prefix, results = main.query_index("https://nonexistent.io/page", exact_match=True)
        assert results == []


def test_query_index_db_offline():
    """ValueError when GLOBAL_DB is None."""
    with patch("app.main.GLOBAL_DB", None):
        with pytest.raises(ValueError, match="Database engine is offline"):
            main.query_index("https://example.com")


def test_lookup_endpoint_exact():
    """GET /lookup returns 200 with valid response structure."""
    catalog = {1: "/data/warc.warc.gz"}
    db_items: dict[bytes, bytes] = {
        _make_key("https://example.com/page", "20260801120000"): _make_value(1, 0, 500),
    }
    with patch("app.main.GLOBAL_DB", MockRdict(db_items)), patch("app.main.ID_TO_PATH", catalog):
        client = TestClient(main.app)
        resp = client.get("/lookup", params={"url": "https://example.com/page", "exact": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_url"] == "https://example.com/page"
        assert body["surt_prefix"] == "com,example)/page"
        assert body["exact_match"] is True
        assert body["total_results"] == 1
        assert len(body["results"]) == 1
        assert body["results"][0]["timestamp"] == "20260801120000"


def test_lookup_endpoint_not_found():
    """GET /lookup returns 404 when no captures match."""
    db_items: dict[bytes, bytes] = {}
    catalog: dict[int, str] = {}
    with patch("app.main.GLOBAL_DB", MockRdict(db_items)), patch("app.main.ID_TO_PATH", catalog):
        client = TestClient(main.app)
        resp = client.get("/lookup", params={"url": "https://missing.io/x"})
        assert resp.status_code == 404


def test_lookup_endpoint_db_offline():
    """GET /lookup returns 500 when DB is offline."""
    with patch("app.main.GLOBAL_DB", None):
        client = TestClient(main.app)
        resp = client.get("/lookup", params={"url": "https://example.com"})
        assert resp.status_code == 500


def test_lookup_endpoint_limit_param():
    """Limit parameter is respected via the API."""
    catalog = {1: "/data/w.warc.gz"}
    db_items: dict[bytes, bytes] = {
        _make_key("https://example.com/a", "20260101000000"): _make_value(1, 0, 100),
        _make_key("https://example.com/b", "20260201000000"): _make_value(1, 100, 200),
        _make_key("https://example.com/c", "20260301000000"): _make_value(1, 300, 300),
    }
    with patch("app.main.GLOBAL_DB", MockRdict(db_items)), patch("app.main.ID_TO_PATH", catalog):
        client = TestClient(main.app)
        resp = client.get("/lookup", params={"url": "https://example.com", "exact": False, "limit": 2})
        assert resp.status_code == 200
        assert resp.json()["total_results"] == 2


def test_lookup_endpoint_at_param():
    """at= timestamp parameter is passed through."""
    catalog = {1: "/data/w.warc.gz"}
    db_items: dict[bytes, bytes] = {
        _make_key("https://example.com/page", "20260801120000"): _make_value(1, 0, 500),
        _make_key("https://example.com/page", "20260802130000"): _make_value(1, 500, 600),
    }
    with patch("app.main.GLOBAL_DB", MockRdict(db_items)), patch("app.main.ID_TO_PATH", catalog):
        client = TestClient(main.app)
        resp = client.get(
            "/lookup",
            params={"url": "https://example.com/page", "exact": True, "at": "20260802000000"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["at_timestamp"] == "20260802000000"
        # Only entries >= 20260802000000
        assert body["total_results"] == 1
