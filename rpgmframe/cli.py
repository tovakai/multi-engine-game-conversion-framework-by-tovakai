"""Command-line entry point for RPGMFrame."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpgmframe.builder import BuildError, build_game
from rpgmframe.detector import inspect_game
from rpgmframe.packaging import PackagingError, create_tar_gz
from rpgmframe.runtime import DEFAULT_NWJS_VERSION


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpgmframe",
        description="Inspect and convert RPG Maker and Godot games for Linux ARM64.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Detect the supported engine used by a game directory.",
    )
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the inspection result as JSON.",
    )

    build_parser = subparsers.add_parser(
        "build",
        help="Build a Linux ARM64 package with the matching engine runtime.",
    )
    build_parser.add_argument("path", type=Path, help="Game directory or .zip archive")
    build_parser.add_argument(
        "--runtime",
        type=Path,
        help="Use this extracted Linux ARM64 runtime instead of the cache (NW.js or mkxp-z)",
    )
    build_parser.add_argument(
        "--runtime-version",
        default=DEFAULT_NWJS_VERSION,
        help=(
            "NW.js version for MV/MZ when --runtime is omitted; "
            "XP/VX/VX Ace use RPGMFrame's pinned mkxp-z artifact; "
            "Godot uses the exact version read from its PCK "
            f"(default NW.js: {DEFAULT_NWJS_VERSION})"
        ),
    )
    build_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory (default: <source>-frame)",
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory/archive",
    )
    build_parser.add_argument(
        "--archive",
        action="store_true",
        help="Also create a portable Linux ARM64 .tar.gz beside the build",
    )

    return parser


def _print_inspection(result) -> None:
    print(f"Source:        {result.source_path}")
    print(f"Engine:        {result.engine.value}")
    print(f"Runtime:       {result.runtime or 'unknown'}")
    print(f"Confidence:    {result.confidence.value}")
    print(f"Compatibility: {result.compatibility.value}")
    if result.game_root:
        print(f"Game root:     {result.game_root}")
    if result.game_name:
        print(f"Game name:     {result.game_name}")
    if result.engine_version:
        print(f"Engine version: {result.engine_version}")
    if result.package_json:
        print(f"package.json:  {result.package_json}")

    if result.evidence:
        print("Evidence:")
        for item in result.evidence:
            print(f"  - {item}")

    if result.warnings:
        print("Warnings:")
        for item in result.warnings:
            print(f"  - {item}")


def _print_build(result, archive_path: Path | None = None) -> None:
    print(f"Built:         {result.output_path}")
    print(f"Engine:        {result.engine.value}")
    if result.engine_version:
        print(f"Engine version: {result.engine_version}")
    print(f"Runtime:       {result.runtime_path}")
    print(f"Runtime arch:  {result.runtime_architecture}")
    print(f"Launcher:      {result.launcher_path}")
    if archive_path:
        print(f"Archive:       {archive_path}")
    if result.game_name:
        print(f"Game name:     {result.game_name}")
    if result.warnings:
        print("Warnings:")
        for item in result.warnings:
            print(f"  - {item}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "inspect":
        result = inspect_game(args.path)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            _print_inspection(result)
        return 0 if result.recognized else 2

    if args.command == "build":
        try:
            result = build_game(
                args.path,
                runtime=args.runtime,
                runtime_version=args.runtime_version,
                output=args.output,
                force=args.force,
                progress=lambda message: print(message, file=sys.stderr),
            )
            archive_path = (
                create_tar_gz(result.output_path, force=args.force)
                if args.archive
                else None
            )
        except (BuildError, PackagingError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        _print_build(result, archive_path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
