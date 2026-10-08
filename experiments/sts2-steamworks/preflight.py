"""Read-only source validation, before any downloads or compilation."""

import argparse
import json
from pathlib import Path
import sys

from converter_io import safe, relative, read_verified, verified_stream

HERE = Path(__file__).resolve().parent


def inspect_source(source, *, full=True, profile=None):
    profile = profile or json.loads((HERE / "converter_profile_v1.json").read_bytes())
    source = safe(source)
    report = {"release": None, "commit": None, "supported": False,
              "source_verified": False, "errors": [], "files_checked": 0}
    try:
        metadata = source / "release_info.json"
        if metadata.stat().st_size > 4096:
            raise ValueError("Release metadata exceeds limit")
        metadata = safe(metadata)
        release = json.loads(metadata.read_bytes())
        report.update(release=release.get("version"), commit=release.get("commit"))
        if (report["release"], report["commit"]) != (profile["release"], profile["commit"]):
            raise ValueError("Unsupported STS2 build: only v0.98.2 / f4eeecc6 is supported")
        pin = next(p for p in profile["copy_files"] if p["source"] == "release_info.json")
        read_verified(source / "release_info.json", pin)
        report["supported"] = True
    except (OSError, ValueError, StopIteration) as error:
        report["errors"].append(str(error))
        return report
    if not full:
        return report
    records = [(p["source"], p) for p in profile["copy_files"]]
    records += [("data_sts2_windows_x86_64/" + n, p) for n, p in profile["managed_inputs"].items()]
    records.append(("SlayTheSpire2.pck", profile["pack"]))
    for name, pin in records:
        try:
            with verified_stream(source / relative(name), pin):
                pass
            report["files_checked"] += 1
        except (OSError, ValueError) as error:
            report["errors"].append({"file": name, "error": str(error)})
    report["source_verified"] = not report["errors"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_source(args.source, full=not args.metadata_only)
    except (OSError, ValueError) as error:
        report = {"supported": False, "source_verified": False, "errors": [str(error)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
