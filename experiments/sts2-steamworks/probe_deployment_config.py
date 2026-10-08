import hashlib, json, os, stat
from pathlib import Path

ROOT = Path("/run/media/steamos/SD512/sts2-arm64-proto")
FILES = {
    "launch.sh": "12e60dc157fb56b77078b09ee57d4bbbf8b77d0f99be840e710280398947df08",
    "release_info.json": "abd1cfcc2327940c6d2ec95e371c50f07455b670980782e68d6daa7b437dda6c",
    "addons/sentry/sentry.gdextension": "614952c9df2b7da5af6f831bb75487845233c4d49a1b86987a8a2f38531125c9",
    "sentry-original-manifest/addons/sentry/sentry.gdextension": "39ee709ec6706630a001e6a7f7116a01250751ebf2bb232c82465c9d8c63b3eb",
    "sentry-original-manifest/sentry-arm64.gdextension": "afeceb8ec9095aaac5f1ed57c2d79f152844de1bd78fd57442a0687d3da726bc",
    "data_sts2_linuxbsd_arm64/sts2.runtimeconfig.json": "bd81a252bc3f0e8bcb649b404c1da945913c5377b9d3a2c416c52730be8714c0",
    "data_sts2_linuxbsd_arm64/sts2.deps.json": "ae899ff7301d1506b22d3a229ea3b4cd240f4e9585b8b9268506a7154ff65870",
    "data_sts2_linuxbsd_arm64/Microsoft.NETCore.App.runtimeconfig.json": "ca4b32d5e1a9fe69521ed95c23914097b822fb1d593ff59b1ea236a3a48c786e",
    "data_sts2_linuxbsd_arm64/Microsoft.NETCore.App.deps.json": "fdeb49420909f712ab9a6e6f64780b307e2f9b6a6d21c0d73f584900ae07bbd4",
}

def deps_summary(value):
    return {"runtimeTarget": value.get("runtimeTarget"), "targets": [
        {"name": target, "library_count": len(libraries),
         "runtime_packages": [name for name in libraries if "Microsoft.NETCore.App" in name],
         "native_assets": {name: data["native"] for name, data in libraries.items() if "native" in data},
         "runtime_target_assets": {name: data["runtimeTargets"] for name, data in libraries.items() if "runtimeTargets" in data}}
        for target, libraries in value.get("targets", {}).items()]}

def collect(root, files=None):
    report = {"diagnostic_version": 1, "files": [], "errors": [],
              "scope": "Read-only named deployment configs and launcher text; no Steam calls, binary execution, environment dump, or writes."}
    for relative, expected in (FILES if files is None else files).items():
        path = root / relative
        try:
            if any(p.is_symlink() for p in (path, *path.parents) if p == root or root in p.parents):
                raise ValueError("symbolic link refused")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size > 1048576:
                    raise ValueError("expected a regular config file under 1 MiB")
                raw = stream.read(1048577)
                after = os.fstat(stream.fileno())
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if stamp(before) != stamp(after) or stamp(after) != stamp(path.lstat()):
                raise ValueError("file changed; close STS2 and rerun")
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("hash differs from the supplied inventory; contents withheld")
            text = raw.decode("utf-8-sig")
            value = json.loads(text) if relative.endswith(".json") else text
            if relative.endswith(".deps.json"):
                value = deps_summary(value)
            report["files"].append({"path": relative, "sha256": expected, "contents": value})
        except (OSError, ValueError, TypeError, AttributeError) as error:
            message = "read failed: errno=" + str(error.errno) if isinstance(error, OSError) else str(error)
            report["errors"].append({"path": relative, "error": message})
    return report

if __name__ == "__main__":
    result = collect(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(2 if result["errors"] else 0)
