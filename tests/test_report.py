"""Tests for cdx_rocks.report — SURT host-pattern statistics."""

import json
from typing import cast

from cdx_rocks.report import (
    REPORT_FILENAME,
    ReportCounter,
    load_report,
    looks_like_surt,
    surt_browse,
    surt_host_patterns,
    write_report,
)


class TestSurtHostPatterns:
    """Verify host extraction and label-prefix expansion."""

    def test_host_with_path_suffix(self):
        assert surt_host_patterns("com,example)/page") == ["com", "com,example"]

    def test_bare_host(self):
        assert surt_host_patterns("com,desample)") == ["com", "com,desample"]

    def test_multi_level_host(self):
        assert surt_host_patterns("zw,co,zifmstereo)") == ["zw", "zw,co", "zw,co,zifmstereo"]

    def test_all_numeric_host_counts_full_only(self):
        assert surt_host_patterns("82,2,237,15)") == ["82,2,237,15"]

    def test_all_numeric_host_with_path(self):
        assert surt_host_patterns("82,2,237,15)/path") == ["82,2,237,15"]

    def test_mixed_numeric_and_alpha_counts_prefixes(self):
        # Only hosts that are entirely numeric skip sub-prefixes
        assert surt_host_patterns("com,123)/x") == ["com", "com,123"]

    def test_empty_string(self):
        assert surt_host_patterns("") == []

    def test_empty_host(self):
        assert surt_host_patterns(")/page") == []

    def test_split_only_on_first_paren(self):
        assert surt_host_patterns("com,example)/a)b") == ["com", "com,example"]


class TestReportCounter:
    """Verify counting, merging, and serialization."""

    def test_user_example_counts(self):
        counter = ReportCounter()
        counter.record("com,example)")
        counter.record("com,desample)")
        counter.record("org,example)")

        assert counter.total_entries == 3
        assert counter.patterns == {
            "com": 2,
            "com,example": 1,
            "com,desample": 1,
            "org": 1,
            "org,example": 1,
        }

    def test_numeric_host_skips_sub_prefixes(self):
        counter = ReportCounter()
        counter.record("82,2,237,15)")
        counter.record("82,2,237,15)/path")

        assert counter.total_entries == 2
        assert counter.patterns == {"82,2,237,15": 2}

    def test_merge(self):
        a = ReportCounter()
        a.record("com,example)")
        b = ReportCounter()
        b.record("com,desample)")
        b.record("org,example)")

        a.merge(b)
        assert a.total_entries == 3
        assert a.patterns == {
            "com": 2,
            "com,example": 1,
            "com,desample": 1,
            "org": 1,
            "org,example": 1,
        }

    def test_to_dict_sorted_by_count_desc(self):
        counter = ReportCounter()
        counter.record("org,example)")
        counter.record("com,example)")
        counter.record("com,desample)")

        data = counter.to_dict()
        assert data["total_entries"] == 3
        patterns = cast("dict[str, int]", data["patterns"])
        # Ties broken alphabetically; com(2) first
        assert list(patterns.keys()) == ["com", "com,desample", "com,example", "org", "org,example"]

    def test_roundtrip_from_dict(self):
        counter = ReportCounter()
        counter.record("com,example)")
        counter.record("82,2,237,15)")

        restored = ReportCounter.from_dict(counter.to_dict())
        assert restored.total_entries == counter.total_entries
        assert restored.patterns == counter.patterns

    def test_from_dict_tolerates_missing_fields(self):
        counter = ReportCounter.from_dict({})
        assert counter.total_entries == 0
        assert counter.patterns == {}


class TestReportFile:
    """Verify load/write of the JSON artifact."""

    def test_filename_constant(self):
        assert REPORT_FILENAME == "surt_report.json"

    def test_write_and_load_roundtrip(self, tmp_path):
        counter = ReportCounter()
        counter.record("com,example)")
        counter.record("com,desample)")

        path = tmp_path / REPORT_FILENAME
        write_report(path, counter)

        loaded = load_report(path)
        assert loaded.total_entries == 2
        assert loaded.patterns == counter.patterns

    def test_write_is_valid_json(self, tmp_path):
        counter = ReportCounter()
        counter.record("com,example)")

        path = tmp_path / REPORT_FILENAME
        write_report(path, counter)

        data = json.loads(path.read_text())
        assert data["total_entries"] == 1
        assert data["patterns"]["com"] == 1

    def test_load_missing_file_returns_empty(self, tmp_path):
        loaded = load_report(tmp_path / "nope.json")
        assert loaded.total_entries == 0
        assert loaded.patterns == {}

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        path = tmp_path / REPORT_FILENAME
        path.write_text("not json{{{")
        loaded = load_report(path)
        assert loaded.total_entries == 0
        assert loaded.patterns == {}

    def test_load_wrong_shape_returns_empty(self, tmp_path):
        path = tmp_path / REPORT_FILENAME
        path.write_text("[1, 2, 3]")
        loaded = load_report(path)
        assert loaded.total_entries == 0


class TestLooksLikeSurt:
    """Verify URL vs SURT key auto-detection."""

    def test_surt_forms_detected(self):
        assert looks_like_surt("com,example")
        assert looks_like_surt("com,yahoo,news")
        assert looks_like_surt("com,example)/page1")
        assert looks_like_surt("82,2,237,15)")

    def test_urls_not_detected(self):
        assert not looks_like_surt("https://example.com/page1")
        assert not looks_like_surt("http://www.yahoo.com/")
        assert not looks_like_surt("example.com/page1")
        assert not looks_like_surt("com")
        assert not looks_like_surt("")

    def test_scheme_wins_over_comma(self):
        # A URL with a comma in the path still has a scheme, so stays a URL
        assert not looks_like_surt("https://en.wikipedia.org/wiki/A,_B")


class TestSurtBrowse:
    """Verify one-hop tree traversal over a report dict."""

    REPORT = {
        "total_entries": 7,
        "patterns": {
            "com": 3,
            "com,example": 2,
            "com,desample": 1,
            "org": 1,
            "org,other": 1,
            "org,deep": 0,  # zero-count entries can exist; order by count desc
            "82,2,237,15": 2,  # dotted-IP host: only the full host is counted
        },
    }

    def test_root_lists_top_level_labels(self):
        result = surt_browse("", self.REPORT)
        assert result["pattern"] == ""
        assert result["count"] == 0
        assert result["total_children"] == 3
        children = cast("dict[str, int]", result["children"])
        # com(3) first, then 82,2,237,15(2), then org(1)
        assert list(children) == ["com", "82,2,237,15", "org"]
        assert children["com"] == 3
        assert children["org"] == 1

    def test_orphan_numeric_host_promoted_to_root(self):
        # 82,2,237,15 has no parent in the report (numeric hosts skip
        # sub-prefixes), so it must appear at the root to stay reachable
        result = surt_browse("", self.REPORT)
        children = cast("dict[str, int]", result["children"])
        assert "82,2,237,15" in children
        assert children["82,2,237,15"] == 2

    def test_one_level_down(self):
        result = surt_browse("com", self.REPORT)
        assert result["pattern"] == "com"
        assert result["count"] == 3
        assert result["children"] == {"com,example": 2, "com,desample": 1}
        assert result["total_children"] == 2

    def test_leaf_host_has_no_children(self):
        result = surt_browse("com,example", self.REPORT)
        assert result["count"] == 2
        assert result["children"] == {}
        assert result["total_children"] == 0

    def test_unknown_pattern_empty(self):
        result = surt_browse("net", self.REPORT)
        assert result["count"] == 0
        assert result["children"] == {}

    def test_limit_caps_children(self):
        result = surt_browse("", self.REPORT, limit=1)
        children = cast("dict[str, int]", result["children"])
        assert len(children) == 1
        assert list(children) == ["com"]
        assert result["total_children"] == 3

    def test_deeper_level_excludes_grandchildren(self):
        report = {
            "total_entries": 1,
            "patterns": {"uk": 1, "uk,co": 1, "uk,co,dailymail": 1},
        }
        result = surt_browse("uk", report)
        assert result["children"] == {"uk,co": 1}
        result = surt_browse("uk,co", report)
        assert result["children"] == {"uk,co,dailymail": 1}

    def test_missing_patterns_field(self):
        result = surt_browse("", {"total_entries": 0})
        assert result["children"] == {}
        assert result["count"] == 0
