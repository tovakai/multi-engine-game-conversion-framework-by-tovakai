#!/usr/bin/env python3
"""Source-to-AArch64 pipeline; vendor FMOD SDK permissions remain required."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build_native import build, STEAM_API
from converter_io import safe
from convert_sts2 import convert, create_tar
from fetch_converter_runtimes import fetch
from preflight import inspect_source
from sdk_archive import prepare_sdk


def run(source, output, *, sdk, cache, scons="scons", steam_api=STEAM_API,
        authorized=False, progress=None):
    progress = progress or (lambda message: None)
    if not authorized:
        raise ValueError("Game ownership and vendor dependency permissions must be acknowledged")
    source, output, cache, sdk = map(safe, (source, output, cache, sdk))
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Output must be new with an existing parent")
    for root in (source, sdk, cache):
        if root == output or root in output.parents or output in root.parents:
            raise ValueError("Output must be separate from all inputs and cache")
    if source == cache or source in cache.parents or cache in source.parents:
        raise ValueError("Cache must be separate from source")
    progress("Verifying supported original source files")
    report = inspect_source(source)
    if report["errors"]:
        raise ValueError("Source validation failed: " + json.dumps(report, sort_keys=True))
    cache.mkdir(parents=True, exist_ok=True)
    # Keep failed build logs for diagnostics. No existing build is reused.
    parent = Path(tempfile.mkdtemp(prefix="sts2-build-", dir=cache))
    sdk = prepare_sdk(sdk, parent / "vendor-sdk")
    progress("Compiling pinned ARM64 Spine and FMOD sources; logs: " + str(parent / "work/build.log"))
    native, profile, evidence = build(parent / "work", sdk, steam_api=steam_api, scons=scons)
    progress("Downloading and verifying official Godot, .NET and Sentry runtimes")
    archives = fetch(cache / "runtimes")
    progress("Transforming managed code and pack; validating native output")
    result = convert(source, output, native, archives, authorized=True,
                     _profile=profile, _native_build=evidence)
    result["source_validation"] = report
    result["build_workspace"] = str(parent)
    result["limitations"] = ["Vendor FMOD SDK and applicable FMOD/Spine permissions are required.",
                              "Startup, Steam initialization and gameplay need device acceptance."]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fmod-sdk", type=Path, default=os.environ.get("MEGCFBT_STS2_FMOD_SDK"))
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/megcfbt/sts2")
    parser.add_argument("--scons", default=os.environ.get("MEGCFBT_STS2_SCONS", "scons"))
    parser.add_argument("--steam-api", type=Path, default=STEAM_API)
    parser.add_argument("--acknowledge-licenses", action="store_true")
    parser.add_argument("--tar", type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.fmod_sdk:
            raise ValueError("FMOD Studio API 2.03.15 Linux SDK is required. Official downloads require sign-in at https://www.fmod.com/download; no experimental binaries are accepted.")
        if args.tar:
            target, output = safe(args.tar), safe(args.output)
            if target.exists() or not target.parent.is_dir() or target == output or output in target.parents:
                raise ValueError("Transfer archive must be new, outside output, with existing parent")
            for root in (safe(args.source), safe(args.fmod_sdk), safe(args.cache)):
                if target == root or root in target.parents:
                    raise ValueError("Transfer archive must be outside all inputs and cache")
        result = run(args.source, args.output, sdk=args.fmod_sdk, cache=args.cache,
                     scons=args.scons, steam_api=args.steam_api, authorized=args.acknowledge_licenses,
                     progress=lambda message: print(message, file=sys.stderr, flush=True))
        if args.tar:
            result["transfer_archive"] = create_tar(args.output, args.tar)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        result = {"errors": [str(error)], "output_exists": args.output.exists()}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
