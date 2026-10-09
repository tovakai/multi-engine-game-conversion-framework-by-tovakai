"""Summarize diagnostic JSONL; timings are inclusive and must not be added.

Input-to-next-draw includes menus and the first transition frame. It is NOT
an automatic measurement of the time until a new area is fully interactive.
"""
import argparse
import collections
import json
import math
import re
from pathlib import Path


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def summarize(path):
    # A live run can have a partially written final line. Skip only that line.
    lines = path.read_text().splitlines()
    records = []
    for number, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if number != len(lines) - 1:
                raise
    aggregates = [row for row in records if row["type"] == "aggregate"]
    draws = [row["duration_ms"] for row in records if row["type"] == "first_draw_after_input"]
    result = dict(path=str(path), last_aggregate=aggregates[-1] if aggregates else None,
                  input_to_next_draw=dict(count=len(draws), p50_ms=percentile(draws, 0.5),
                                          p95_ms=percentile(draws, 0.95), max_ms=max(draws) if draws else None),
                  unavailable_hooks=[row["operation"] for row in records if row["type"] == "unavailable_hook"])
    process_path = Path(str(path) + ".process.jsonl")
    if process_path.exists():
        samples = [json.loads(line) for line in process_path.read_text().splitlines()]
        samples = [row for row in samples if row["type"] == "process"]
        rss = []
        read_bytes = []
        for row in samples:
            match = re.search(r"^VmRSS:\s+(\d+)", row.get("status", ""), re.M)
            if match:
                rss.append(int(match.group(1)))
            match = re.search(r"^read_bytes:\s+(\d+)", row.get("io", ""), re.M)
            if match:
                read_bytes.append(int(match.group(1)))
        result["process"] = dict(samples=len(samples), peak_rss_mib=max(rss)/1024 if rss else None,
                                 physical_read_mib=(read_bytes[-1]-read_bytes[0])/2**20 if read_bytes else None,
                                 wait_channels=collections.Counter(row.get("wchan", "").strip() for row in samples))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps([summarize(path) for path in args.traces], indent=2))
