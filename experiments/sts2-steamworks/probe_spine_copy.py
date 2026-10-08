"""Bounded static Spine copy/build hashes; no code execution or writes."""
import hashlib, json, os, stat
from pathlib import Path
ROOT = Path("/run/media/steamos/SD512/spine-arm64-build/spine-runtimes")
PROTO = Path("/run/media/steamos/SD512/sts2-arm64-proto")
LIB = "bin/linux/libspine_godot.linux.template_release.arm64.so"
EXPECTED = "5af1a01af371ee9469021705ac6de8fc3cf7aa642362b1b4ea461adb2cbb3a3a"
SUFFIXES = {".c", ".cpp", ".h", ".hpp", ".inc", ".inl"}
def safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError("Symbolic link refused")

def fingerprint(path):
    safe(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024 * 1024: raise ValueError("Non-regular or oversized file refused")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not fields(before) == fields(opened) == fields(after) == fields(path.stat()) or len(raw) != before.st_size: raise ValueError("File changed during inspection")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
def source_tree(root):
    safe(root)
    if not root.is_dir(): raise ValueError("Source directory missing")
    records, entries = {}, 0
    def failed(error): raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        entries += 1 + len(dirs) + len(files)
        if entries > 4096: raise ValueError("Source traversal limit exceeded")
        for name in dirs + files: safe(Path(directory) / name)
        for name in files:
            path = Path(directory) / name
            if path.suffix in SUFFIXES: records[path.relative_to(root).as_posix()] = fingerprint(path)
    if not records: raise ValueError("No selected source files found")
    return records
def collect(root, prototype):
    report = {"diagnostic_version": 1, "errors": [], "sources": {}, "files": [],
              "scope": "Read-only bounded hashes of selected C/C++ files, optional build inputs and three library paths. No source contents disclosed, compilation, library loading, Steam calls or writes; matching hashes do not prove a reproducible build."}
    trees = {}
    for label, relative in (("original", "spine-cpp/spine-cpp"), ("copied", "spine-godot/spine_godot/spine-cpp")):
        try:
            trees[label] = source_tree(root / relative)
            raw = json.dumps(trees[label], sort_keys=True, separators=(",", ":")).encode()
            report["sources"][label] = {"file_count": len(trees[label]), "tree_sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError) as error: report["errors"].append(label + ": " + type(error).__name__)
    if len(trees) == 2:
        differences = sorted(p for p in trees["original"].keys() | trees["copied"].keys() if trees["original"].get(p) != trees["copied"].get(p))
        report.update(source_copy_matches=not differences, difference_count=len(differences), difference_paths=differences[:20])
    for label, path in [("build", root / "spine-godot" / LIB), ("example", root / "spine-godot/example-v4-extension" / LIB), ("deployed", prototype / LIB)] + [(p, root / "spine-godot" / p) for p in ("custom.py", "godot-cpp/dev", "godot-cpp/gdextension/extension_api.json")]:
        row = {"label": label, "path": str(path)}
        report["files"].append(row)
        try:
            safe(path)
            row["present"] = path.exists()
            if row["present"]:
                row.update(fingerprint(path))
                if label in {"build", "example", "deployed"}:
                    row["matches_prototype_inventory"] = row["sha256"] == EXPECTED and row["size_bytes"] == 4328984
        except (OSError, ValueError) as error:
            row["error"] = type(error).__name__
            report["errors"].append(label + ": " + type(error).__name__)
    return report
if __name__ == "__main__": print(json.dumps(collect(ROOT, PROTO), indent=2, sort_keys=True))
