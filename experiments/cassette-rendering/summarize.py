"""Summarize private trial logs without copying proprietary shader source."""
import argparse
import json
from pathlib import Path
import re
import statistics


def summarize(root):
    result = {}
    for path in sorted(root.glob("*-session.txt")):
        text = path.read_text(errors="replace")
        fps = [int(value) for value in re.findall(r"Project FPS:\s*(\d+)", text)]
        errors = sorted(set(re.findall(r"(?:SHADER ERROR:|ERROR:|WARNING:) [^\r\n]*", text)))
        result[path.name] = {
            "utc_launch": re.findall(r"^UTC: (.*)$", text, re.MULTILINE),
            "fps_scope": "Entire launch session including loading/menu; not a controlled benchmark",
            "fps_samples": len(fps),
            "fps_min": min(fps) if fps else None,
            "fps_median": statistics.median(fps) if fps else None,
            "fps_max": max(fps) if fps else None,
            "diagnostics": errors,
        }
    probes = []
    for path in sorted(root.glob("*/logs/*.log")):
        for line in path.read_text(errors="replace").splitlines():
            if "CASSETTE_RENDER_PROBE " in line:
                probes.append({"variant": path.parent.parent.name,
                               "settings": json.loads(line.split("CASSETTE_RENDER_PROBE ", 1)[1])})
    return {"sessions": result, "probes": probes,
            "graphical_correctness_requires_human_testing": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.root), indent=2))
