#!/usr/bin/env python3
"""Locate stats-related assemblies without loading code or changing files."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys


ROOT = Path("/run/media/steamos/SD512/sts2-arm64-proto")
DATA_NAME = "data_sts2_linuxbsd_arm64"
CLIENT_HASH = "7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5"
LIBRARY_HASH = "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b"
MARKERS = (
    "SteamStatsManager", "SteamAchievementManager", "RequestCurrentStats",
    "UserStatsReceived_t", "UserStatsStored_t", "UserAchievementStored_t",
)


def scan(path, chunk_size=1024 * 1024):
    if path.is_symlink():
        raise ValueError("Refusing to follow a symbolic-link file")
    needles = {name: name.encode("ascii") for name in MARKERS}
    overlap = max(map(len, needles.values())) - 1
    digest = hashlib.sha256()
    found = set()
    tail = b""
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        while True:
            block = stream.read(chunk_size)
            if not block:
                break
            digest.update(block)
            window = tail + block
            found.update(name for name, needle in needles.items() if needle in window)
            tail = window[-overlap:]
        after = os.fstat(stream.fileno())
    current = path.stat()
    def identity(value):
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
    if path.is_symlink() or identity(before) != identity(after) or identity(after) != identity(current):
        raise ValueError("File changed during inspection; rerun with STS2 closed")
    return {
        "path": str(path), "size_bytes": after.st_size,
        "sha256": digest.hexdigest(), "identifier_hits": sorted(found),
    }


def collect(root, frame_host="steamos@FRAME_HOST"):
    report = {
        "diagnostic_version": 1,
        "root": str(root),
        "scope": "Read-only file hashes and identifier search; no IL conclusions, library loading, Steam initialization, or file writes.",
        "assemblies_scanned": 0, "assemblies": [], "errors": [],
        "transfer_requests": [], "game_assembly_candidates_found": False,
    }
    if not root.is_dir():
        report["errors"].append("Prototype directory is missing or inaccessible")
        return report
    data = root / DATA_NAME
    wrapper = data / "Steamworks.NET.dll"
    library = data / "libsteam_api64.so"
    for name, path, expected in (
        ("working_wrapper", wrapper, CLIENT_HASH),
        ("native_library", library, LIBRARY_HASH),
    ):
        try:
            item = scan(path)
            item["matches_expected_hash"] = item["sha256"] == expected
            report[name] = item
        except (OSError, ValueError) as error:
            report["errors"].append(str(path) + ": " + str(error))

    def walk_error(error):
        report["errors"].append(str(error))

    for directory, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != ".git")
        for name in sorted(files):
            if not name.lower().endswith(".dll"):
                continue
            path = Path(directory) / name
            try:
                item = scan(path)
                report["assemblies_scanned"] += 1
                if item["identifier_hits"] or path == wrapper:
                    report["assemblies"].append(item)
                if item["identifier_hits"] and name.lower() != "steamworks.net.dll":
                    report["transfer_requests"].append({
                        **item, "reason": "Candidate game stats/callback code; identifiers are not proof of declarations or call sites.",
                    })
            except (OSError, ValueError) as error:
                report["errors"].append(str(path) + ": " + str(error))

    if "native_library" in report:
        report["transfer_requests"].append({
            **report["native_library"],
            "reason": "Static inspection of the remaining native stats accessor ABI.",
        })
    report["game_assembly_candidates_found"] = any(
        item["path"].lower().endswith(".dll") for item in report["transfer_requests"]
    )
    for index, item in enumerate(report["transfer_requests"], 1):
        destination = "./sts2-inspection-{:02d}-{}".format(index, Path(item["path"]).name)
        item["scp_from_your_computer"] = shlex.join([
            "scp", "--", frame_host + ":" + item["path"], destination,
        ])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--frame-host", default="steamos@FRAME_HOST")
    args = parser.parse_args(argv)
    report = collect(args.root, args.frame_host)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["errors"] or not report["game_assembly_candidates_found"] else 0


if __name__ == "__main__":
    sys.exit(main())
