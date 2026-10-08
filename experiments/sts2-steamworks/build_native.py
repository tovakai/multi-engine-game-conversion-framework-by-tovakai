"""Build pinned STS2 extensions from source in a new Linux AArch64 workspace.

FMOD's licensed SDK is a vendor input, not a previous conversion artifact.
Steam API comes from the installed Valve runtime and remains hash pinned.
"""

import argparse
import copy
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from adapt_fmod_build_sources import adapt_sources, RECIPES, SOURCE_COMMIT, GODOT_CPP_COMMIT
from converter_io import safe, read_verified, write_new
from convert_sts2 import load_profile, require_elf
from verify_output import inspect

SPINE_COMMIT = "e7dc1435fa4a0083ab431f1b28e083c14a1f5c68"
SPINE_CPP_COMMIT = "27d9dd23c83871e0619fca5dc2cddfbfd69e926a"
STEAM_API = Path("/opt/steamvr/bin/linuxarm64/libsteam_api.so")
HERE = Path(__file__).resolve().parent


def command(args, cwd, log, *, env=None):
    with log.open("ab") as output:
        output.write(("\n$ " + json.dumps([str(a) for a in args]) + "\n").encode())
        output.flush()
        result = subprocess.run([str(a) for a in args], cwd=cwd, stdout=output,
                                stderr=subprocess.STDOUT, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def checkout(url, commit, destination, log):
    # No mutable tags, submodule recursion, existing worktree or prior build output.
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ValueError("Source checkout destination is not empty")
    else:
        destination.mkdir()
    command(["git", "init", "--quiet"], destination, log)
    command(["git", "fetch", "--depth=1", url, commit], destination, log)
    command(["git", "checkout", "--detach", "FETCH_HEAD"], destination, log)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination, text=True).strip()
    if actual != commit:
        raise ValueError("Source commit mismatch")


def sdk_file(root, name):
    # Vendor SDK uses relative .so aliases. Resolve only within the selected SDK.
    root = safe(root)
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("FMOD SDK alias escapes selected SDK")
    return safe(path)


def sdk_headers(sdk):
    pins = json.loads((HERE / "fmod_sdk_headers_v1.json").read_bytes())
    actual = {p.relative_to(sdk).as_posix() for section in ("core", "studio")
              for p in (sdk / "api" / section / "inc").glob("*") if p.suffix in {".h", ".hpp"}}
    if actual != set(pins):
        raise ValueError("FMOD SDK build-header inventory differs from pinned vendor SDK")
    return {name: read_verified(sdk_file(sdk, name), pin) for name, pin in pins.items()}


def build(work, sdk, *, steam_api=STEAM_API, scons="scons", jobs=4):
    if platform.system() != "Linux" or platform.machine() not in {"aarch64", "arm64"}:
        raise ValueError("Extension compilation currently requires a Linux AArch64 host")
    if not 1 <= jobs <= 16:
        raise ValueError("Build jobs must be between 1 and 16")
    work, sdk = safe(work), safe(sdk)
    if work == sdk or sdk in work.parents or work in sdk.parents:
        raise ValueError("Build workspace must be separate from SDK")
    profile = copy.deepcopy(load_profile())
    # Verify proprietary inputs before any network or source execution.
    steam_pin = next(p for p in profile["native_files"] if p["provider_name"] == "libsteam_api64.so")
    steam = read_verified(steam_api, steam_pin)
    require_elf(steam, "Steam platform API")
    headers = sdk_headers(sdk)
    vendor = {}
    for section, name in (("core", "libfmod.so.14"), ("studio", "libfmodstudio.so.14")):
        pin = next(p for p in profile["native_files"] if p["provider_name"] == name)
        vendor[name] = read_verified(sdk_file(sdk, f"api/{section}/lib/arm64/{name}"), pin)
        require_elf(vendor[name], name)
    scons = shutil.which(str(scons))
    if not scons:
        raise ValueError("SCons is required in an isolated build environment; tested version is 4.11.1")
    for tool in ("git", "g++", "readelf"):
        if not shutil.which(tool):
            raise ValueError("Missing build tool: " + tool)
    work.mkdir()  # Exclusive, never reuse a previous build.
    log = work / "build.log"
    versions = {}
    for tool in ("git", "g++", "readelf", scons):
        versions[tool] = subprocess.check_output([tool, "--version"], text=True).splitlines()[0:3]
    evidence = {"recipe": "sts2-native-source-v1", "toolchain": versions,
                "python": sys.version,
                "host": platform.platform(), "commands_log": "build.log", "sources": {},
                "scope": "Fresh source builds. Byte-reproducible compilation and gameplay are not claimed."}
    env = dict(os.environ, SOURCE_DATE_EPOCH="1759276800", LC_ALL="C", TZ="UTC")
    spine = work / "spine-runtimes"
    fmod = work / "fmod-gdextension"
    for label, url, commit, path in (
        ("spine", "https://github.com/EsotericSoftware/spine-runtimes.git", SPINE_COMMIT, spine),
        ("spine-godot-cpp", "https://github.com/godotengine/godot-cpp.git", SPINE_CPP_COMMIT, spine / "spine-godot/godot-cpp"),
        ("fmod", "https://github.com/utopia-rise/fmod-gdextension.git", SOURCE_COMMIT, fmod),
        ("fmod-godot-cpp", "https://github.com/godotengine/godot-cpp.git", GODOT_CPP_COMMIT, fmod / "godot-cpp"),
    ):
        checkout(url, commit, path, log)
        evidence["sources"][label] = {"url": url, "commit": commit}
    # Equivalent to upstream setup-extension.sh without mutable branch fetches
    # or its rm -rf operations, and build only the required release target.
    shutil.copytree(spine / "spine-cpp/spine-cpp", spine / "spine-godot/spine_godot/spine-cpp")
    resources, patches = adapt_sources({name: (fmod / name).read_bytes() for name in RECIPES})
    for name in RECIPES:
        (fmod / name).write_bytes(resources[name])
    evidence["fmod_patches"] = patches
    layout = work / "sdk-layout"
    for section, name in (("core", "libfmod"), ("studio", "libfmodstudio")):
        inc = layout / "linux" / section / "inc"
        inc.mkdir(parents=True)
        for name, raw in headers.items():
            if name.startswith(f"api/{section}/inc/"):
                write_new(inc / Path(name).name, raw)
        lib = layout / "linux" / section / "lib/arm64"
        write_new(lib / (name + ".so"), vendor[name + ".so.14"])
        write_new(lib / (name + ".so.14"), vendor[name + ".so.14"])
    flags = ["platform=linux", "arch=arm64", "target=template_release", f"-j{jobs}"]
    evidence["build_arguments"] = flags
    evidence["vendor_inputs"] = {"steam_api": {"provider": str(steam_api), **inspect(safe(steam_api))},
                                "sdk_headers": {p.relative_to(layout).as_posix(): inspect(p)
                                                for p in sorted(layout.rglob("*")) if p.is_file()}}
    command([scons, *flags], spine / "spine-godot", log, env=env)
    command([scons, *flags, "fmod_lib_dir=" + str(layout) + "/"], fmod, log, env=env)
    natives = work / "native"
    natives.mkdir()
    extension_paths = {
        "libspine_godot.linux.template_release.arm64.so": spine / "spine-godot/bin/linux/libspine_godot.linux.template_release.arm64.so",
        "libGodotFmod.linux.template_release.arm64.so": fmod / "demo/addons/fmod/libs/linux/libGodotFmod.linux.template_release.arm64.so",
    }
    exports = {"libspine_godot.linux.template_release.arm64.so": "spine_godot_library_init",
               "libGodotFmod.linux.template_release.arm64.so": "fmod_library_init"}
    evidence["native_dynamic_sections"] = {}
    evidence["matches_previous_extension_hashes"] = {}
    for name, path in extension_paths.items():
        raw = safe(path).read_bytes()
        require_elf(raw, name)
        symbols = subprocess.check_output(["readelf", "--dyn-syms", "--wide", path], text=True)
        if not any(line.split()[-1:] == [exports[name]] and " UND " not in line for line in symbols.splitlines()):
            raise ValueError("Built extension lacks entry symbol: " + exports[name])
        write_new(natives / name, raw)
        pin = next(p for p in profile["native_files"] if p["provider_name"] == name)
        evidence["matches_previous_extension_hashes"][name] = inspect(natives / name)["sha256"] == pin["sha256"]
        evidence["native_dynamic_sections"][name] = subprocess.check_output(
            ["readelf", "--dynamic", "--wide", path], text=True)
        pin.update({k: v for k, v in inspect(natives / name).items() if k in {"sha256", "size_bytes"}})
    for name, raw in {**vendor, "libsteam_api64.so": steam}.items():
        write_new(natives / name, raw)
    evidence["outputs"] = {p.name: inspect(p) for p in sorted(natives.iterdir())}
    write_new(work / "native-build.json", (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode())
    return natives, profile, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--fmod-sdk", type=Path, required=True)
    parser.add_argument("--steam-api", type=Path, default=STEAM_API)
    parser.add_argument("--scons", default="scons")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        native, profile, evidence = build(args.work, args.fmod_sdk, steam_api=args.steam_api, scons=args.scons, jobs=args.jobs)
        write_new(args.work / "generated-profile.json", (json.dumps(profile, indent=2, sort_keys=True) + "\n").encode())
        result = {"errors": [], "native_dir": str(native), "evidence": evidence}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result = {"errors": [str(error)], "workspace": str(args.work)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
