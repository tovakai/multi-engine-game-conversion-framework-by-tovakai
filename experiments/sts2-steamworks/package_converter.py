#!/usr/bin/env python3
"""Package conversion software only, using a fixed source/document allowlist."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from converter_io import safe, publish_new
from verify_output import inspect


FILES = (
    "convert_sts2.py", "converter_io.py", "converter_profile_v1.json", "fetch_converter_runtimes.py",
    "verify_output.py", "prepare_managed.py", "patch_accessors.py", "patch_stats.py", "patch_pack.py",
    "adapt_packed_manifests.py", "adapt_deployment_graph.py", "inspect_dependency_graph.py",
    "inventory_package.py", "STANDALONE.md", "HANDOFF.md",
    "pipeline.py", "preflight.py", "build_native.py", "adapt_fmod_build_sources.py",
    "fmod_sdk_headers_v1.json", "sdk_archive.py", "SOURCE_PIPELINE.md", "RELEASE_BLOCKERS.md",
    "steam_launch.py",
    "licenses/GODOT-LICENSE.txt", "licenses/GODOT-COPYRIGHT.txt",
    "licenses/SENTRY-LICENSE.md", "licenses/SPINE-LICENSE.txt",
)


def package(destination):
    import os
    destination = safe(destination)
    here = Path(__file__).resolve().parent
    fd, name = tempfile.mkstemp(prefix=".sts2-software-", suffix=".zip", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, path in [(name, here / name) for name in FILES] + [("LICENSE", here.parents[1] / "LICENSE")]:
                info = zipfile.ZipInfo("sts2-converter/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        result = inspect(temporary)
        publish_new(temporary, destination)
        return {"errors": [], "software_archive": str(destination), **result,
                "scope": "Conversion source, hash metadata, documentation and AGPL license only; no game or dependency binaries."}
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        result = package(args.destination)
    except (OSError, ValueError) as error:
        result = {"errors": [str(error)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
