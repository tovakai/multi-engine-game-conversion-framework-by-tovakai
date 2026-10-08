#!/usr/bin/env python3
"""Standalone, out-of-place conversion for the hash-pinned STS2 v0.98.2 recipe."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile

from adapt_deployment_graph import adapt_deps
from converter_io import safe, relative, verified_stream, read_verified, write_new, publish_new
from patch_pack import rewrite_pack
from prepare_managed import prepare_pair
from verify_output import MANIFEST, inspect, verify


HERE = Path(__file__).resolve().parent
PROFILE = HERE / "converter_profile_v1.json"
DATA = "data_sts2_linuxbsd_arm64"
SOURCE_DATA = "data_sts2_windows_x86_64"
LAUNCH = b'''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ "$(uname -m)" != aarch64 && "$(uname -m)" != arm64 ]]; then
    printf '%s\\n' 'This converted game requires Linux ARM64.' >&2
    exit 2
fi
if [[ "${SteamAppId:-}" != 2868840 ]]; then
    printf '%s\\n' 'Launch this conversion through the owned Slay the Spire 2 Steam library entry (AppID 2868840).' >&2
    exit 2
fi
if [[ -n "${SteamGameId:-}" && "${SteamGameId}" != 2868840 ]]; then
    printf '%s\\n' 'Conflicting SteamGameId; refusing launch.' >&2
    exit 2
fi
DATA="$ROOT/data_sts2_linuxbsd_arm64"
export LD_LIBRARY_PATH="$ROOT/addons/fmod/libs/linux:$ROOT/addons/sentry/bin/linux/arm64:$ROOT/bin/linux:$DATA:$ROOT:${LD_LIBRARY_PATH:-}"
cd -- "$ROOT"
exec "$ROOT/SlayTheSpire2" --main-pack "$ROOT/SlayTheSpire2.pck" --display-driver x11 "$@"
'''
COLLECT = b'''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
mkdir -p -- "$ROOT/diagnostics"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 "$ROOT/verify_output.py" "$ROOT" --diagnostics > "$ROOT/diagnostics/$STAMP.json"
printf 'Diagnostic report: %s\\n' "$ROOT/diagnostics/$STAMP.json"
set +e
"$ROOT/launch.sh" --verbose "$@" 2>&1 | tee "$ROOT/diagnostics/$STAMP.log"
STATUSES=("${PIPESTATUS[@]}")
set -e
printf 'Game exit code: %s; log writer exit code: %s\\n' "${STATUSES[0]}" "${STATUSES[1]}"
if [[ "${STATUSES[0]}" != 0 ]]; then exit "${STATUSES[0]}"; fi
exit "${STATUSES[1]}"
'''
NOTICES = b'''STS2 ARM64 personal conversion: v0.98.2 / f4eeecc6

This output contains your game and explicitly supplied dependencies. Do not
redistribute it as a game package. The converter distributes no game binaries,
FMOD SDK/runtime, Spine binary, or Steam API binary. You are responsible for
your game license and dependency permissions, including the Spine Runtimes
License and FMOD Studio API terms. No license is granted by this converter.

Official inputs: Godot 4.5.1 Mono (MIT plus third-party components), Microsoft
.NET runtime 9.0.7 (MIT plus third-party components), Sentry Godot 1.5.0 (MIT
plus bundled native/Crashpad notices). Preserve and review the notices in the
original distributions before any permitted redistribution. The full downloaded
archives remain with the user; this file is not a substitute for their notices.
The licenses directory preserves pinned Godot/Sentry/Spine license texts,
Godot third-party copyrights, .NET license/notices and the converter's AGPL.
These notices do not grant FMOD or Spine permissions or establish that all
proprietary/game/native dependency notice obligations have been satisfied.

Steam authentication/ownership checks are not bypassed. Launch using your owned
Steam AppID 2868840 entry. The launcher checks its context, not ownership itself.
Original stats/achievement code is preserved except the verified initialization
adaptation to a real GetStat read; no successful callbacks or stats are invented.
The observed input contains NullAchievementStrategy; achievement behavior is not
established. Hash matching identifies this recipe, not publisher authenticity.

No saves, Steam credentials, or user data are copied by the converter.
Output integrity verification does not establish gameplay, auth, cloud sync,
achievement support or actual-device compatibility. Validate these separately.
'''


def load_profile():
    return json.loads(PROFILE.read_bytes())


def executable(path):
    return path in {"SlayTheSpire2", "launch.sh", "collect-startup.sh"} or path.endswith(("/crashpad_handler", "/createdump"))


def require_elf(raw, label):
    if len(raw) < 20 or raw[:6] != b"\x7fELF\x02\x01" or raw[18:20] != b"\xb7\0":
        raise ValueError("Expected verified AArch64 ELF: " + label)


def extract_members(archive, records, stage):
    names = [item.filename for item in archive.infolist()]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate archive member")
    for item in records:
        relative(item["member"])
        target = stage / relative(item["destination"])
        info = archive.getinfo(item["member"])
        if info.file_size != item["size_bytes"] or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
            raise ValueError("Wrong size, symlink or encrypted archive member")
        if info.file_size > 64 * 1024 * 1024:
            raise ValueError("Archive member exceeds limit")
        raw = archive.read(info)
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Archive member hash mismatch: " + item["member"])
        if raw.startswith(b"\x7fELF"):
            require_elf(raw, item["member"])
        write_new(target, raw, 0o755 if executable(item["destination"]) else 0o644)


def create_tar(root, destination):
    root, destination = safe(root), safe(destination)
    if destination == root or root in destination.parents or destination.exists():
        raise ValueError("Transfer archive must be new and outside the output")
    report = verify(root)
    if report["errors"]:
        raise ValueError("Output verification failed before archive creation")
    manifest = json.loads((root / MANIFEST).read_bytes())
    fd, name = tempfile.mkstemp(prefix=".sts2-transfer-", suffix=".tar", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with tarfile.open(temporary, "w", format=tarfile.PAX_FORMAT) as archive:
            def portable(info):
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                path = info.name.removeprefix("sts2-arm64/")
                info.mode = 0o755 if executable(path) else 0o644
                return info
            for item in [*manifest["files"], {"path": MANIFEST}]:
                path = root / relative(item["path"])
                safe(path)
                archive.add(path, arcname="sts2-arm64/" + item["path"], recursive=False, filter=portable)
        digest = inspect(temporary)
        publish_new(temporary, destination)
        return {"path": str(destination), **digest}
    finally:
        temporary.unlink(missing_ok=True)


def convert(source, output, native_dir, archives, *, authorized=False, _profile=None, _pack_transform=None):
    if not authorized:
        raise ValueError("Acknowledge legitimate game ownership and dependency permissions with --acknowledge-licenses")
    profile = load_profile() if _profile is None else _profile
    source, output, native_dir = safe(source), safe(output), safe(native_dir)
    if not source.is_dir() or not native_dir.is_dir() or not output.parent.is_dir():
        raise ValueError("Source/native directory and output parent must exist")
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    for input_root in (source, native_dir):
        if input_root == output or input_root in output.parents or output in input_root.parents:
            raise ValueError("Output must be separate from the source and dependency directories")
    copies = {item["destination"]: read_verified(source / relative(item["source"]), item)
              for item in profile["copy_files"]}
    original = {name: read_verified(source / SOURCE_DATA / relative(name), pin)
                for name, pin in profile["managed_inputs"].items()}
    managed = prepare_pair(original["sts2.dll"], original["Steamworks.NET.dll"])
    deps = adapt_deps(original["sts2.deps.json"], mode=profile["deps_mode"])
    deps_report = {"mode": profile["deps_mode"], "sha256": hashlib.sha256(deps).hexdigest()}
    natives = {}
    for item in profile["native_files"]:
        raw = read_verified(native_dir / relative(item["provider_name"]), item)
        require_elf(raw, item["provider_name"])
        natives[item["destination"]] = raw
    legal = {}
    for item in profile["legal_files"]:
        path = HERE / relative(item["source"])
        if item["source"] == "LICENSE" and not path.exists():
            path = HERE.parents[1] / "LICENSE"
        legal[item["destination"]] = read_verified(path, item)
    pack = source / "SlayTheSpire2.pck"
    safe(pack)
    if pack.stat().st_size != profile["pack"]["size_bytes"]:
        raise ValueError("Unsupported source pack size")
    stage = None
    try:
        with ExitStack() as stack:
            opened = {}
            for key, recipe in profile["archives"].items():
                path = safe(archives[key])
                if output == path or output in path.parents:
                    raise ValueError("Archive input conflicts with output")
                stream = stack.enter_context(verified_stream(path, recipe["pin"]))
                opened[key] = stack.enter_context(zipfile.ZipFile(stream))
            stage = Path(tempfile.mkdtemp(prefix=".sts2-conversion-", dir=output.parent))
            for name, raw in {**copies, **natives, **legal, **{DATA + "/" + n: raw for n, raw in managed.items()},
                              DATA + "/sts2.deps.json": deps}.items():
                write_new(stage / relative(name), raw, 0o755 if executable(name) else 0o644)
            for key, archive in opened.items():
                extract_members(archive, profile["archives"][key]["members"], stage)
            kwargs = {"transform": _pack_transform} if _pack_transform is not None else {}
            pack_report = rewrite_pack(pack, stage / "SlayTheSpire2.pck", expected_sha256=profile["pack"]["sha256"],
                                       expected_size=profile["pack"]["size_bytes"], atomic_publication=False, **kwargs)
            for name, raw in {"launch.sh": LAUNCH, "collect-startup.sh": COLLECT,
                              "verify_output.py": (HERE / "verify_output.py").read_bytes(), "CONVERSION-NOTICES.txt": NOTICES}.items():
                write_new(stage / name, raw, 0o755 if executable(name) else 0o644)
        # The input archive descriptors have now also passed their closing identity checks.
        files = []
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            name = path.relative_to(stage).as_posix()
            files.append({"path": name, "executable": executable(name), **inspect(path)})
        manifest = {"manifest_version": 1, "converter_recipe": "sts2-standalone-v1", "release": profile["release"],
                    "commit": profile["commit"], "appid": profile["appid"], "files": files,
                    "source_pack": profile["pack"], "pack_adaptation": pack_report, "deps_adaptation": deps_report,
                    "scope": "Locally staged conversion. No game execution, ownership, authentication, achievements or Frame validation claimed."}
        write_new(stage / MANIFEST, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        validation = verify(stage)
        if validation["errors"]:
            raise ValueError("Staged output verification failed: " + str(validation["errors"]))
        publish_new(stage, output)
        stage = None
        return {"errors": [], "output": str(output), "validation": validation,
                "scope": manifest["scope"]}
    finally:
        if stage is not None:
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Clean matching-build game directory")
    parser.add_argument("output", type=Path, help="New directory, outside all input trees")
    parser.add_argument("--native-dir", type=Path, required=True, help="Flat directory containing the five authorized native dependencies")
    parser.add_argument("--godot-templates", type=Path, required=True)
    parser.add_argument("--dotnet-runtime", type=Path, required=True)
    parser.add_argument("--sentry-archive", type=Path, required=True)
    parser.add_argument("--acknowledge-licenses", action="store_true")
    parser.add_argument("--tar", type=Path, help="Optional new, uncompressed transfer archive with Linux permissions")
    args = parser.parse_args(argv)
    try:
        if args.tar:
            tar_path = safe(args.tar)
            output = safe(args.output)
            if tar_path.exists() or output == tar_path or output in tar_path.parents or not tar_path.parent.is_dir():
                raise ValueError("Transfer archive path must be new, outside output, with an existing parent")
            for root in (safe(args.source), safe(args.native_dir)):
                if root == tar_path or root in tar_path.parents:
                    raise ValueError("Transfer archive must be outside all input trees")
        result = convert(args.source, args.output, args.native_dir,
                         {"godot": args.godot_templates, "dotnet": args.dotnet_runtime, "sentry": args.sentry_archive},
                         authorized=args.acknowledge_licenses)
        if args.tar:
            result["transfer_archive"] = create_tar(args.output, args.tar)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        result = {"errors": [str(error)], "output_exists": args.output.exists(),
                  "scope": "Conversion refused or failed; originals never edited. A completed output may remain if optional archive creation failed."}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
