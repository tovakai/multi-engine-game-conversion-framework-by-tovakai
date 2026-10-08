#!/usr/bin/env python3
"""Read the installed wrapper hash and Steam-related startup log context."""

import hashlib
import json
from pathlib import Path


ASSEMBLY = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/Steamworks.NET.dll")
LOG = Path("/tmp/sts2-arm64-gui.log")
ORIGINAL_HASH = "474a2af1328c2a2b32bedf8376ed46a50958423313856659ac05bee677d8fdd3"
PATCHED_HASH = "808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de"


def main():
    report = {"assembly": str(ASSEMBLY), "log": str(LOG), "errors": []}
    try:
        digest = hashlib.sha256()
        with ASSEMBLY.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        value = digest.hexdigest()
        report["assembly_sha256"] = value
        report["assembly_state"] = {
            ORIGINAL_HASH: "original", PATCHED_HASH: "generic-accessor-patch-v1",
            "7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5": "client023-v2",
            "e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14": "stats013-v3-wrapper",
        }.get(value, "unrecognized")
    except OSError as error:
        report["errors"].append(str(error))
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = set()
        for index, line in enumerate(lines):
            if any(term in line.casefold() for term in (
                "steam", "exception", "failedgeneric", "breakpad",
            )):
                selected.update(range(max(0, index - 3), min(len(lines), index + 9)))
        report["log_line_count"] = len(lines)
        report["matching_context_line_count"] = len(selected)
        indices = sorted(selected)[-120:] if selected else list(range(max(0, len(lines) - 40), len(lines)))
        report["log_context"] = [{"line": index + 1, "text": lines[index]} for index in indices]
    except OSError as error:
        report["errors"].append(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
