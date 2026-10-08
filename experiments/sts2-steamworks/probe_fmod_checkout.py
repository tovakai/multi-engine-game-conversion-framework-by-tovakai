"""Read-only FMOD Git metadata and bounded SConstruct diff; no SDK inspection."""
import hashlib, json, os, subprocess
from pathlib import Path
ROOT = Path("/run/media/steamos/SD512/fmod-arm64-build")
EXPECTED = "fda1f89a08c0048ed313b333f90b7a7258ce2e61"
SKIP = {".git", "sdk-layout", "sdk", "api", "libs", "demo", "bin", "gen", ".cache"}
def git(folder, *args):
    value = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(folder), *args], capture_output=True, text=True, timeout=120)
    if value.returncode: raise ValueError("Git exit=" + str(value.returncode))
    return value.stdout
def collect(root):
    report = {"diagnostic_version": 1, "repositories": [], "errors": [], "search_incomplete": False,
              "scope": "Bounded read-only Git search within the FMOD build workspace, with SConstruct diff only at the expected extension commit. No SDK contents, logs, remote URLs, fetches, builds, Steam calls or writes. Optional locks/fsmonitor and external diff/text conversion disabled."}
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        report["errors"].append("Build directory missing or symbolic link refused")
        return report
    def failed(error):
        report["search_incomplete"] = True
        report["errors"].append("Traversal failed: errno=" + str(error.errno))
    visited = 0
    for directory, dirs, _ in os.walk(root, followlinks=False, onerror=failed):
        visited += 1
        if visited > 500:
            report["search_incomplete"] = True
            break
        folder = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (folder / d).is_symlink())
        if len(folder.relative_to(root).parts) >= 3: dirs[:] = []
        if not (folder / ".git").exists() or (folder / ".git").is_symlink(): continue
        row = {"checkout": str(folder), "errors": []}
        report["repositories"].append(row)
        commands = {"commit": ["rev-parse", "HEAD"], "branch": ["branch", "--show-current"],
                    "tracked_changes": ["status", "--porcelain=v1", "--untracked-files=no", "--ignore-submodules=all"],
                    "submodules": ["submodule", "status", "--recursive"],
                    "untracked_build_paths": ["ls-files", "--others", "--exclude-standard", "-z", "--", "src", "SConstruct", "SConscript", "custom.py"]}
        for key, args in commands.items():
            try:
                text = git(folder, *args)
                if key == "untracked_build_paths":
                    paths = sorted(p for p in text.split("\0") if p)
                    row.update(untracked_build_count=len(paths), untracked_build_paths=paths[:40], untracked_listing_truncated=len(paths) > 40)
                else: row[key] = text.strip().splitlines() if key in {"tracked_changes", "submodules"} else text.strip()
            except (OSError, ValueError, subprocess.TimeoutExpired) as error: row["errors"].append(key + ": " + type(error).__name__)
        if row.get("commit") == EXPECTED:
            try:
                diff = git(folder, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "HEAD", "--", "SConstruct")
                row.update(matches_expected_extension_commit=True, sconstruct_diff=diff[:8192], sconstruct_diff_truncated=len(diff) > 8192, sconstruct_diff_sha256=hashlib.sha256(diff.encode()).hexdigest())
            except (OSError, ValueError, subprocess.TimeoutExpired) as error: row["errors"].append("SConstruct diff: " + type(error).__name__)
    report["directories_visited"] = visited
    report["repositories"].sort(key=lambda row: row["checkout"])
    return report
if __name__ == "__main__": print(json.dumps(collect(ROOT), indent=2, sort_keys=True))
