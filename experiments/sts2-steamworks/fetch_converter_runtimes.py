#!/usr/bin/env python3
"""Download the three pinned official archives, never native proprietary inputs."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

from converter_io import safe, verified_stream, publish_new


def fetch(cache):
    cache = safe(cache)
    cache.mkdir(parents=True, exist_ok=True)
    profile = json.loads((Path(__file__).parent / "converter_profile_v1.json").read_bytes())
    names = {"godot": "Godot_v4.5.1-stable_mono_export_templates.tpz",
             "dotnet": "microsoft.netcore.app.runtime.linux-arm64.9.0.7.nupkg",
             "sentry": "sentry-godot-1.5.0+6c4d74e.zip"}
    result = {}
    for key, recipe in profile["archives"].items():
        destination = cache / names[key]
        if destination.exists():
            with verified_stream(destination, recipe["pin"]):
                pass
        else:
            fd, name = tempfile.mkstemp(prefix=".sts2-download-", dir=cache)
            temporary = Path(name)
            try:
                request = urllib.request.Request(recipe["url"], headers={"User-Agent": "STS2-ARM64-converter/1"})
                with os.fdopen(fd, "wb") as output, urllib.request.urlopen(request, timeout=60) as response:
                    if not response.geturl().startswith("https://"):
                        raise ValueError("Non-HTTPS download redirect refused")
                    total = 0
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > recipe["pin"]["size_bytes"]:
                            raise ValueError("Download exceeds pinned size")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                with verified_stream(temporary, recipe["pin"]):
                    pass
                publish_new(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        result[key] = str(destination)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args(argv)
    try:
        result = {"errors": [], "archives": fetch(args.cache)}
    except (OSError, ValueError) as error:
        result = {"errors": [str(error)], "scope": "Existing cached files were not overwritten."}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
