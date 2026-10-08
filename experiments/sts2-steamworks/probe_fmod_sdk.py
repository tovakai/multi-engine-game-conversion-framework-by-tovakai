"""Read-only selected FMOD SDK/layout/output fingerprints; never load libraries."""
import hashlib, json, os, re, stat
from pathlib import Path
BASE = Path("/run/media/steamos/SD512/fmod-arm64-build")
PROTO = Path("/run/media/steamos/SD512/sts2-arm64-proto")
EXTENSION = "libGodotFmod.linux.template_release.arm64.so"
EXPECTED = {"extension": ("0d5be1a919feb1d287e29b8115441c4e99d8795b8fcad031fc74699ca2a2cf62", 3281280),
            "core": ("3f890c918d513aa1e6c6efba330f9869ff15258d49bf3e2b52f9bee832c90de5", 1290880),
            "studio": ("d1bc3c729d534d9f03933d24cbc84139f73a460f92334e09ccdf388c334dcd31", 1302256)}
def inspect(path, boundary, kind):
    row = {"path": str(path), "kind": kind, "present": path.exists()}
    if not row["present"] and not path.is_symlink(): return row
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(boundary.resolve()): raise ValueError("Alias outside allowed root refused")
    row["resolved_relative"] = resolved.relative_to(boundary.resolve()).as_posix()
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024 * 1024: raise ValueError("Non-regular or oversized file refused")
    with resolved.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not fields(before) == fields(opened) == fields(after) == fields(resolved.stat()) or len(raw) != before.st_size or path.resolve(strict=True) != resolved: raise ValueError("File or alias changed")
    row.update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    if kind == "header":
        row["fmod_version_definitions"] = [token.decode("ascii") for token in re.findall(rb"(?m)^\s*#\s*define\s+FMOD_VERSION\s+(0x[0-9a-fA-F]+)\b", raw)]
    else:
        row["matches_prototype_inventory"] = (row["sha256"], len(raw)) == EXPECTED[kind]
        if len(raw) >= 20 and raw[:4] == b"\x7fELF" and raw[4] in (1, 2) and raw[5] in (1, 2):
            row["elf"] = {"class_bits": 32 if raw[4] == 1 else 64, "machine": int.from_bytes(raw[18:20], "little" if raw[5] == 1 else "big")}
    return row
def collect(base, prototype):
    report = {"diagnostic_version": 1, "files": [], "errors": [],
              "scope": "Read-only selected SDK header hashes/version tokens, explicit SDK aliases and build/deployed library hashes. Aliases confined to the build or prototype root; external targets refused. No SDK contents disclosed, library loading, compilation, Steam calls or writes. Not a complete SDK inventory, license grant or reproducible-build validation."}
    for root in (base, prototype):
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            report["errors"].append("Allowed root missing or symbolic link refused")
            return report
    layout = base / "sdk-layout/linux"
    items = [(layout / section / "inc" / name, base, "header") for section, names in
             (("core", ("fmod.h", "fmod_common.h", "fmod_errors.h")), ("studio", ("fmod_studio.h", "fmod_studio_common.h"))) for name in names]
    for section, stem in (("core", "libfmod"), ("studio", "libfmodstudio")):
        items += [(layout / section / "lib/arm64" / (stem + suffix), base, section) for suffix in (".so", ".so.14")]
    items.append((base / "fmod-gdextension/demo/addons/fmod/libs/linux" / EXTENSION, base, "extension"))
    items += [(prototype / "addons/fmod/libs/linux" / name, prototype, kind) for name, kind in
              ((EXTENSION, "extension"), ("libfmod.so.14", "core"), ("libfmodstudio.so.14", "studio"))]
    for path, boundary, kind in items:
        try: report["files"].append(inspect(path, boundary, kind))
        except (OSError, ValueError, RuntimeError) as error: report["errors"].append({"path": str(path), "error": type(error).__name__})
    return report
if __name__ == "__main__": print(json.dumps(collect(BASE, PROTO), indent=2, sort_keys=True))
