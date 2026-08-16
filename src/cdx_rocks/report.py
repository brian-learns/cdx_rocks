"""SURT host-pattern statistics report.

Both ``cdx-rocks-build`` and ``cdx-rocks-update`` maintain a JSON artifact
(``surt_report.json`` in the index directory) that counts every host
label-prefix seen in the CDXJ input.

For a SURT like ``com,example)/page`` the host part is everything before the
first ``)`` (a bare host has no suffix at all). The host's labels are counted
cumulatively left to right, so each entry contributes::

    +1 to "com"
    +1 to "com,example"

Hosts made entirely of numeric labels (dotted-IP SURTs such as
``82,2,237,15)``) count only the full host — no sub-prefixes.

The build writes the report fresh; the update loads the existing report and
merges the new file's counts into it, so counts accumulate over
build + every subsequent update. Re-processing the same CDXJ file will
double-count (RocksDB dedupes exact key collisions, the report does not).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REPORT_FILENAME = "surt_report.json"


def surt_host_patterns(surt_url: str) -> list[str]:
    """Return the label-prefix patterns one SURT entry contributes to.

    The host part is everything before the first ``)``. Labels are split on
    ``","``. If every label is numeric, only the full host is returned.
    """
    host = surt_url.split(")", 1)[0]
    labels = [label for label in host.split(",") if label]
    if not labels:
        return []
    if all(label.isdigit() for label in labels):
        return [host]
    patterns: list[str] = []
    acc = ""
    for label in labels:
        acc = f"{acc},{label}" if acc else label
        patterns.append(acc)
    return patterns


class ReportCounter:
    """Aggregated counts of SURT host label-prefix patterns."""

    def __init__(self) -> None:
        self.patterns: dict[str, int] = {}
        self.total_entries = 0

    def record(self, surt_url: str) -> None:
        """Add one entry's contribution to the counters."""
        patterns = surt_host_patterns(surt_url)
        if not patterns:
            return
        for pattern in patterns:
            self.patterns[pattern] = self.patterns.get(pattern, 0) + 1
        self.total_entries += 1

    def merge(self, other: ReportCounter) -> None:
        """Add another counter's totals into this one."""
        for pattern, count in other.patterns.items():
            self.patterns[pattern] = self.patterns.get(pattern, 0) + count
        self.total_entries += other.total_entries

    def to_dict(self) -> dict[str, object]:
        """Serialize to the report JSON shape (patterns sorted by count desc)."""
        return {
            "total_entries": self.total_entries,
            "patterns": dict(sorted(self.patterns.items(), key=lambda kv: (-kv[1], kv[0]))),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ReportCounter:
        """Rebuild a counter from a report dict, tolerating missing fields."""
        counter = cls()
        total = data.get("total_entries", 0)
        if isinstance(total, int):
            counter.total_entries = total
        patterns = data.get("patterns")
        if isinstance(patterns, dict):
            for pattern, count in patterns.items():
                counter.patterns[str(pattern)] = int(count)
        return counter


def load_report(path: str | Path) -> ReportCounter:
    """Load an existing report file, or return an empty counter.

    Missing or unreadable files yield an empty counter (with a warning for
    unreadable ones) so an update can still proceed.
    """
    path = Path(path)
    if not path.is_file():
        return ReportCounter()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"report root must be a dict, got {type(data).__name__}")
        return ReportCounter.from_dict(data)
    except (ValueError, OSError) as e:
        logger.warning("Could not load existing report %s: %s — starting fresh.", path, e)
        return ReportCounter()


def write_report(path: str | Path, counter: ReportCounter) -> None:
    """Write the counter as pretty-printed JSON to *path*."""
    path = Path(path)
    path.write_text(json.dumps(counter.to_dict(), indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Wrote %s: %d entries, %d patterns.",
        path,
        counter.total_entries,
        len(counter.patterns),
    )
