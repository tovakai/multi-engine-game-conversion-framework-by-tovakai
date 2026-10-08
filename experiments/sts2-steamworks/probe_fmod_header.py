"""Read-only hashes/diffs for two public extension files; no SDK inspection."""
import hashlib, json, os, stat, subprocess
from pathlib import Path
ROOT = Path("/run/media/steamos/SD512/fmod-arm64-build/fmod-gdextension")
EXPECTED = "fda1f89a08c0048ed313b333f90b7a7258ce2e61"
FILES = ("SConstruct", "src/helpers/common.h")
def git(root, *args):
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args], capture_output=True, timeout=120)
    if result.returncode: raise ValueError("Git command failed")
    return result.stdout
def safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError("Symbolic link refused")
def read(path):
    safe(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 1048576: raise ValueError("Non-regular or oversized file refused")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(1048577)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not fields(before) == fields(opened) == fields(after) == fields(path.stat()) or len(raw) != before.st_size: raise ValueError("File changed")
    return raw
def collect(root):
    report = {"diagnostic_version": 1, "checkout": str(root), "files": [], "errors": [],
              "scope": "Read-only base/current hashes and bounded HEAD diffs for SConstruct and src/helpers/common.h only. No SDK contents, logs, remote URLs, fetches, builds, Steam calls or writes. Optional locks/fsmonitor, external diff and text conversion disabled."}
    try:
        safe(root)
        safe(root / ".git")
        if not (root / ".git").exists(): raise ValueError("Own Git metadata missing")
        commit = git(root, "rev-parse", "HEAD").decode("ascii").strip()
        report["commit"] = commit
        if commit != EXPECTED: raise ValueError("Unexpected checkout commit; file inspection refused")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        report["errors"].append(type(error).__name__)
        return report
    for name in FILES:
        try:
            current = read(root / name)
            base = git(root, "show", "HEAD:" + name)
            if len(base) > 1048576: raise ValueError("Oversized base refused")
            diff = git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "HEAD", "--", name)
            if current != read(root / name) or git(root, "rev-parse", "HEAD").decode("ascii").strip() != commit: raise ValueError("Checkout changed")
            preview = diff[:8192].decode("utf-8", errors="replace")
            report["files"].append({"path": name, "base_sha256": hashlib.sha256(base).hexdigest(), "base_size_bytes": len(base),
                                    "current_sha256": hashlib.sha256(current).hexdigest(), "current_size_bytes": len(current),
                                    "diff": preview, "diff_sha256": hashlib.sha256(diff).hexdigest(), "diff_truncated": len(diff) > 8192})
        except (OSError, ValueError, subprocess.TimeoutExpired) as error: report["errors"].append(name + ": " + type(error).__name__)
    return report
if __name__ == "__main__": print(json.dumps(collect(ROOT), indent=2, sort_keys=True))
