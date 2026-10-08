"""Read-only Git diagnostic; no fetches, builds or source contents disclosed."""
import json
from pathlib import Path
import subprocess

ROOT = Path("/run/media/steamos/SD512/spine-arm64-build/spine-runtimes")


def collect(root):
    report = {"diagnostic_version": 1, "repositories": [], "errors": [],
              "scope": "Targeted read-only Git diagnostic; no builds, fetches, remote URLs, source contents disclosed or writes. Optional locks, fsmonitor and external diff disabled. This does not attest copied source contents or binary provenance."}
    for folder, scope in ((root, ["spine-godot", "spine-cpp/spine-cpp"]),
                          (root / "spine-godot/godot-cpp", [])):
        row = {"checkout": str(folder), "path_scope": scope, "errors": []}
        report["repositories"].append(row)
        if any(p.is_symlink() for p in (folder, *folder.parents, folder / ".git")):
            row["errors"].append("Symbolic link refused")
            continue
        if not folder.is_dir() or not (folder / ".git").exists():
            row["errors"].append("Checkout with own Git metadata not found")
            continue
        commands = {
            "commit": ["rev-parse", "HEAD"],
            "branch": ["branch", "--show-current"],
            "tracked_changes": ["status", "--porcelain=v1", "--untracked-files=no",
                                "--ignore-submodules=all", "--", *scope],
            "untracked_paths": ["ls-files", "--others", "--exclude-standard", "-z", "--", *scope],
            "submodules": ["submodule", "status", "--recursive"],
        }
        for key, args in commands.items():
            try:
                value = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                                        "-c", "diff.external=", "-C", str(folder), *args],
                                       capture_output=True, text=True, timeout=120)
                if value.returncode:
                    row["errors"].append(key + " failed: exit=" + str(value.returncode))
                elif key == "untracked_paths":
                    paths = sorted(p for p in value.stdout.split("\0") if p)
                    row["untracked_count"] = len(paths)
                    row[key] = paths[:40]
                    row["untracked_listing_truncated"] = len(paths) > 40
                elif key in {"tracked_changes", "submodules"}:
                    row[key] = value.stdout.strip().splitlines()
                else:
                    row[key] = value.stdout.strip()
            except (OSError, subprocess.TimeoutExpired) as error:
                row["errors"].append(key + " failed: " + type(error).__name__)
    return report


if __name__ == "__main__":
    print(json.dumps(collect(ROOT), indent=2, sort_keys=True))
