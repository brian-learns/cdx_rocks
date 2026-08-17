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
from typing import cast

logger = logging.getLogger(__name__)

REPORT_FILENAME = "surt_report.json"


def surt_host_patterns(surt_url: str) -> list[str]:
    """Return the label-prefix patterns one SURT entry contributes to.

    The host part is everything before the first ``)``. Labels are split on
    ``,``. If every label is numeric, only the full host is returned.
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


def surt_browse(pattern: str, report: dict[str, object], limit: int = 50) -> dict[str, object]:
    """One hop down the SURT host tree for a browse endpoint.

    *pattern* is a host label-prefix (comma-joined SURT labels) such as
    ``"com"`` or ``"com,example"``. Returns the pattern's own count, its
    direct children (``pattern,label`` entries), and whether more children
    exist than returned.

    At the root (empty *pattern*) the children are the single-label labels.
    Patterns whose parent chain is missing from the report — the dotted-IP
    hosts that count only their full host — are promoted to the root so
    they stay reachable.
    """
    patterns: dict[str, int] = cast("dict[str, int]", report.get("patterns", {}))
    own_count = patterns.get(pattern, 0) if pattern else 0

    prefix = f"{pattern}," if pattern else ""
    children: dict[str, int] = {}
    for name, count in patterns.items():
        if prefix and name.startswith(prefix):
            rest = name[len(prefix) :]
            if "," not in rest:
                children[name] = count
        elif not prefix and "," not in name:
            children[name] = count

    if not prefix:
        # Promote orphans (dotted-IP hosts) so their entries are not lost
        for name, count in patterns.items():
            if "," in name and name.rsplit(",", 1)[0] not in patterns:
                children.setdefault(name, count)

    ordered = sorted(children.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "pattern": pattern,
        "count": own_count,
        "children": dict(ordered[:limit]),
        "total_children": len(ordered),
    }


class SurtTree:
    """In-memory SURT host tree, built once from a report.

    Precomputes the parent -> children map so each browse request is a dict
    lookup plus an O(limit) slice, instead of an O(N) scan over every pattern
    in the report (N is ~150k patterns on the largest index).

    Mirrors ``surt_browse`` semantics exactly, including the promotion of
    dotted-IP hosts (whose parent was never counted) to the root.
    """

    def __init__(self, total_entries: int, patterns: dict[str, int]) -> None:
        self.total_entries = total_entries
        self.patterns = patterns
        self.children: dict[str, list[tuple[str, int]]] = {}
        self._build()

    def _build(self) -> None:
        """Group patterns by parent and pre-sort each children list."""
        groups: dict[str, list[str]] = {}
        for name in self.patterns:
            parent = name.rsplit(",", 1)[0] if "," in name else ""
            groups.setdefault(parent, []).append(name)

        # Promote orphans (dotted-IP hosts whose parent was never counted)
        # to the root so they stay reachable.
        root = groups.setdefault("", [])
        for parent in list(groups):
            if parent and parent not in self.patterns:
                root.extend(groups[parent])
                del groups[parent]

        for parent, names in groups.items():
            names.sort(key=lambda n: (-self.patterns[n], n))
            self.children[parent] = [(n, self.patterns[n]) for n in names]

    def hop(self, pattern: str, limit: int = 50, offset: int = 0) -> dict[str, object]:
        """One hop down the tree: the pattern's count plus its direct children.

        ``offset`` skips the first *offset* children (rank order: count desc,
        name asc) before ``limit`` is applied. Offsets past the end yield an
        empty ``children`` dict. Returns the same shape as ``surt_browse``.
        """
        kids = self.children.get(pattern, [])
        page = kids[offset : offset + limit]
        return {
            "pattern": pattern,
            "count": self.patterns.get(pattern, 0),
            "children": dict(page),
            "total_children": len(kids),
        }


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
