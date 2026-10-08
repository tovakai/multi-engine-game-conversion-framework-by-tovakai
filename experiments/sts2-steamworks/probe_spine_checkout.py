"""Bounded read-only Spine Git provenance search; no builds, fetches or writes."""

import json
import os
from pathlib import Path
import subprocess


SKIP = {".git", ".cache", ".steam", "Steam", "steamapps", "node_modules", "userdata", "saves", "logs"}
OPERATIONS = {
    "commit": ["rev-parse", "HEAD"],
    "branch": ["branch", "--show-current"],
    "tracked_changes": ["status", "--porcelain=v1", "--untracked-files=no"],
    "submodules": ["submodule", "status", "--recursive"],
}


def collect(roots, max_depth=5, max_directories=5000):
    report = {"diagnostic_version": 1, "checkouts": [], "errors": [], "search_incomplete": False,
              "scope": "Bounded search for spine-runtimes folders and read-only Git metadata. No remote URLs, file contents, builds, fetches, Steam calls or writes; Git optional locks and fsmonitor disabled."}
    seen, visited = set(), 0
    def walk_error(error):
        report["search_incomplete"] = True
        report["errors"].append("Directory traversal failed: errno=" + str(error.errno))
    for root in roots:
        root = Path(root)
        if root.is_symlink() or not root.is_dir():
            continue
        for directory, dirs, _ in os.walk(root, followlinks=False, onerror=walk_error):
            visited += 1
            if visited > max_directories:
                report["search_incomplete"] = True
                break
            folder = Path(directory)
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not (folder / d).is_symlink())
            if len(folder.relative_to(root).parts) >= max_depth:
                dirs[:] = []
            if folder.name != "spine-runtimes" or not (folder / ".git").exists():
                continue
            dirs[:] = []
            if folder in seen or (folder / ".git").is_symlink():
                continue
            seen.add(folder)
            row = {"checkout": str(folder), "errors": []}
            for key, args in OPERATIONS.items():
                try:
                    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                                             "-C", str(folder), *args], capture_output=True, text=True, timeout=20)
                    if result.returncode:
                        row["errors"].append(key + " failed: exit=" + str(result.returncode))
                    else:
                        row[key] = result.stdout.strip().splitlines() if key in {"tracked_changes", "submodules"} else result.stdout.strip()
                except (OSError, subprocess.TimeoutExpired) as error:
                    row["errors"].append(key + " failed: " + type(error).__name__)
            report["checkouts"].append(row)
    report["directories_visited"] = visited
    report["checkouts"].sort(key=lambda row: row["checkout"])
    return report


if __name__ == "__main__":
    print(json.dumps(collect([Path.home(), Path("/run/media/steamos/SD512")]), indent=2, sort_keys=True))
