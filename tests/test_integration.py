"""Integration test: build an index from synthetic CDXJ data, then query it.

Exercises the full pipeline end-to-end:
  catalog loading -> CDXJ parsing -> struct packing -> RocksDB write
  -> RocksDB open/read -> struct unpacking -> query_index response
"""

import io
import json
import sys
from pathlib import Path

import surt
import zstandard as zstd
from fastapi.testclient import TestClient
from rocksdict import AccessType, Options, Rdict

from cdx_rocks import build, index, server
from cdx_rocks.build import build_index

# Grab the original zstd.open saved by conftest
_orig_zstd_open = sys.modules["tests.conftest"]._orig_zstd_open


def _make_cdxj(tmp_path: Path, catalog_path: Path) -> Path:
    """Create a synthetic .cdxj.zst file with a few records."""
    name_to_id = build.load_catalog(str(catalog_path))
    filenames = list(name_to_id.keys())

    records = [
        ("https://example.com/page1", "20260101120000", filenames[0], 100, 500),
        ("https://example.com/page1", "20260102130000", filenames[1], 600, 800),
        ("https://other.org/news", "20260201090000", filenames[2], 1400, 300),
    ]

    cdxj_path = tmp_path / "test.cdxj.zst"
    cctx = zstd.ZstdCompressor(level=1)
    with open(cdxj_path, "wb") as fout:
        with cctx.stream_writer(fout) as writer:
            text_writer = io.TextIOWrapper(writer, encoding="utf-8")
            for url, ts, filename, offset, length in records:
                surt_str = surt.surt(url)
                meta = json.dumps({
                    "filename": filename,
                    "offset": offset,
                    "length": length,
                    "offset_in_warc": offset,
                    "warcproxycdxline": f"WARC/1.0 {url} {ts}",
                })
                text_writer.write(f"{surt_str} {ts} {meta}\n")
            text_writer.flush()

    return cdxj_path


def _load_id_to_path(catalog_path: Path) -> dict[int, str]:
    """Load a zstd-compressed catalog into {id: path}."""
    id_to_path: dict[int, str] = {}
    dctx = zstd.ZstdDecompressor()
    with open(catalog_path, "rb") as fh:
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for global_id, line in enumerate(text_stream, start=1):
                full_path = line.strip()
                if full_path:
                    id_to_path[global_id] = full_path
    return id_to_path


def _clear_state() -> None:
    """Clear app.state for the next test."""
    for attr in ("db", "catalog"):
        if hasattr(server.app.state, attr):
            delattr(server.app.state, attr)


def test_build_and_query_roundtrip(tmp_path: Path):
    """Build an index from synthetic CDXJ data, then query it back."""
    test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
    output_dir = tmp_path / "output"
    cdxj_dir = tmp_path / "cdxj"
    cdxj_dir.mkdir(parents=True)

    # Step 1: Create synthetic CDXJ
    _make_cdxj(cdxj_dir, test_catalog)

    # Step 2: Build the index
    build_index(str(cdxj_dir), str(test_catalog), str(output_dir), struct_format="!HQI")

    # Verify build artifacts exist
    assert (output_dir / "cdx-rocks.json").is_file(), "Manifest not written"
    assert (output_dir / "all_warc_paths.txt.zst").is_file(), "Catalog not copied"
    assert (output_dir / "extent.json").is_file(), "Extent not written"
    assert (output_dir / "rocks").is_dir(), "RocksDB directory not created"

    # Step 3: Open the real DB and catalog
    opts = Options(raw_mode=True)
    db = Rdict(str(output_dir / "rocks"), options=opts, access_type=AccessType.read_only())

    copied_catalog = output_dir / "all_warc_paths.txt.zst"
    id_to_path = _load_id_to_path(copied_catalog)

    server.app.state.db = db
    server.app.state.catalog = id_to_path

    try:
        surt_prefix, results = index.query_index(
            server.app, "https://example.com/page1", exact_match=True
        )
        assert surt_prefix == "com,example)/page1"
        assert len(results) == 2
        assert results[0]["timestamp"] == "20260101120000"
        assert results[1]["timestamp"] == "20260102130000"
        assert "PATH_NOT_FOUND" not in results[0]["warc_path"]
        assert results[0]["offset"] == 100
        assert results[0]["length"] == 500
        assert results[1]["offset"] == 600
        assert results[1]["length"] == 800

        # Query the other domain
        _surt, other_results = index.query_index(
            server.app, "https://other.org/news", exact_match=True
        )
        assert len(other_results) == 1
        assert other_results[0]["timestamp"] == "20260201090000"
        assert other_results[0]["offset"] == 1400
        assert other_results[0]["length"] == 300

    finally:
        db.close()
        _clear_state()


def test_build_writes_extent_json(tmp_path: Path):
    """Verify extent.json is written with correct values after build."""
    test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
    output_dir = tmp_path / "output"
    cdxj_dir = tmp_path / "cdxj"
    cdxj_dir.mkdir(parents=True)

    _make_cdxj(cdxj_dir, test_catalog)
    build_index(str(cdxj_dir), str(test_catalog), str(output_dir), struct_format="!HQI")

    extent_path = output_dir / "extent.json"
    assert extent_path.is_file()

    extent = json.loads(extent_path.read_text())
    assert extent["file_extent"] == 10
    assert extent["file_oldest"].startswith("crawl-data/CC-NEWS/2016/08/")
    assert extent["file_newest"].startswith("crawl-data/CC-NEWS/2016/09/")


def test_build_writes_manifest(tmp_path: Path):
    """Verify cdx-rocks.json manifest is written with correct values."""
    test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
    output_dir = tmp_path / "output"
    cdxj_dir = tmp_path / "cdxj"
    cdxj_dir.mkdir(parents=True)

    _make_cdxj(cdxj_dir, test_catalog)
    build_index(str(cdxj_dir), str(test_catalog), str(output_dir), struct_format="!HQI")

    manifest_path = output_dir / "cdx-rocks.json"
    assert manifest_path.is_file()

    data = json.loads(manifest_path.read_text())
    assert data[0] == "cdx-rocks"
    assert data[1]["catalog"] == "all_warc_paths.txt.zst"
    assert data[1]["db"] == "rocks/"
    assert data[1]["struct_format"] == "!HQI"


def test_update_adds_records(tmp_path: Path):
    """Build an index, then update it with a second CDXJ file."""
    from cdx_rocks.update import update_index

    test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
    output_dir = tmp_path / "output"
    cdxj_dir1 = tmp_path / "cdxj1"
    cdxj_dir2 = tmp_path / "cdxj2"
    cdxj_dir1.mkdir(parents=True)
    cdxj_dir2.mkdir(parents=True)

    # Build initial index
    _make_cdxj(cdxj_dir1, test_catalog)
    build_index(str(cdxj_dir1), str(test_catalog), str(output_dir), struct_format="!HQI")

    # Create a second CDXJ with a different URL
    name_to_id = build.load_catalog(str(test_catalog))
    filenames = list(name_to_id.keys())

    cdxj_file2 = cdxj_dir2 / "extra.cdxj.zst"
    cctx = zstd.ZstdCompressor(level=1)
    with open(cdxj_file2, "wb") as fout:
        with cctx.stream_writer(fout) as writer:
            text_writer = io.TextIOWrapper(writer, encoding="utf-8")
            meta = json.dumps({
                "filename": filenames[3],
                "offset": 5000,
                "length": 1200,
                "offset_in_warc": 5000,
                "warcproxycdxline": "WARC/1.0 https://newsite.com/article 20260301100000",
            })
            surt_str = surt.surt("https://newsite.com/article")
            text_writer.write(f"{surt_str} 20260301100000 {meta}\n")
            text_writer.flush()

    # Update the index — reads manifest from output_dir, copies catalog, writes extent
    update_index(str(cdxj_file2), str(test_catalog), str(output_dir))

    # Verify extent.json was refreshed
    extent = json.loads((output_dir / "extent.json").read_text())
    assert extent["file_extent"] == 10
    assert extent["file_oldest"].startswith("crawl-data/CC-NEWS/2016/08/")

    # Open and verify both old and new records exist
    opts = Options(raw_mode=True)
    db = Rdict(str(output_dir / "rocks"), options=opts, access_type=AccessType.read_only())

    copied_catalog = output_dir / "all_warc_paths.txt.zst"
    id_to_path = _load_id_to_path(copied_catalog)

    server.app.state.db = db
    server.app.state.catalog = id_to_path

    try:
        # Old records still queryable
        _surt, results = index.query_index(
            server.app, "https://example.com/page1", exact_match=True
        )
        assert len(results) == 2

        # New record is present
        _surt, new_results = index.query_index(
            server.app, "https://newsite.com/article", exact_match=True
        )
        assert len(new_results) == 1
        assert new_results[0]["timestamp"] == "20260301100000"
        assert new_results[0]["offset"] == 5000
        assert new_results[0]["length"] == 1200

    finally:
        db.close()
        _clear_state()


def test_lookup_endpoint_after_real_build(tmp_path: Path):
    """Full pipeline test via the FastAPI /lookup endpoint."""
    test_catalog = Path(__file__).parent / "test_warc_paths.txt.zst"
    output_dir = tmp_path / "output"
    cdxj_dir = tmp_path / "cdxj"
    cdxj_dir.mkdir(parents=True)

    _make_cdxj(cdxj_dir, test_catalog)
    build_index(str(cdxj_dir), str(test_catalog), str(output_dir), struct_format="!HQI")

    # Open real DB and catalog
    opts = Options(raw_mode=True)
    db = Rdict(str(output_dir / "rocks"), options=opts, access_type=AccessType.read_only())

    copied_catalog = output_dir / "all_warc_paths.txt.zst"
    id_to_path = _load_id_to_path(copied_catalog)

    server.app.state.db = db
    server.app.state.catalog = id_to_path

    try:
        client = TestClient(server.app)
        resp = client.get(
            "/cdx-index/lookup",
            params={"url": "https://example.com/page1", "exact": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_url"] == "https://example.com/page1"
        assert body["surt_prefix"] == "com,example)/page1"
        assert body["total_results"] == 2
        assert body["results"][0]["offset"] == 100
        assert body["results"][1]["offset"] == 600
    finally:
        db.close()
        _clear_state()
