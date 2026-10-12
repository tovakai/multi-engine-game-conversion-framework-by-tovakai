"""Resolve provenance before freezing; official tag builds fail before packaging."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from megcfbt.version import packaged_build_info, validate_release


def write_identity(target, output, tag=None):
    info = packaged_build_info(target)
    if tag:
        validate_release(tag, info)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["windows-x64", "linux-aarch64"], required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/_build_info.json")
    parser.add_argument("--release-tag", default=os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None)
    args = parser.parse_args()
    write_identity(args.platform, args.output, args.release_tag)
