#!/usr/bin/env python3
"""CLI entry: python -m renpy_arm … or python -m app.main for GUI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from renpy_arm.convert import FRAME_INSTRUCTIONS, ConvertError, convert_game


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert a Ren'Py PC build to Linux aarch64 zip")
    p.add_argument("source", type=Path, help="Game folder or .zip")
    p.add_argument("-o", "--output", type=Path, help="Output zip path")
    p.add_argument("--version", help="Ren'Py version override (e.g. 8.5.3)")
    p.add_argument("--force", action="store_true", help="Re-download SDK")
    p.add_argument("--cache-dir", type=Path, help="SDK cache directory")
    args = p.parse_args(argv)
    try:
        result = convert_game(
            args.source,
            output_zip=args.output,
            version_override=args.version,
            cache_dir=args.cache_dir,
            force=args.force,
            log=print,
        )
    except ConvertError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print()
    print(FRAME_INSTRUCTIONS)
    print("Archive:", result.archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
