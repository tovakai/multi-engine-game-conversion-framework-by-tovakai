"""Command-line interface for Multi-Engine Game Conversion Framework by Tovakai."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpgmframe.runtime import DEFAULT_NWJS_VERSION

from .builder import BuildError, build_game
from .detector import inspect_source

APP_NAME = "Multi-Engine Game Conversion Framework by Tovakai"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multi-engine-game-conversion-framework-by-tovakai",
        description=(
            "Inspect and convert Ren'Py, RPG Maker, and Godot games to "
            "native Linux ARM64 packages."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Detect the game engine and conversion backend.")
    inspect_p.add_argument("path", type=Path)
    inspect_p.add_argument("--json", action="store_true")

    build_p = sub.add_parser("build", help="Convert a supported game for Linux ARM64.")
    build_p.add_argument("path", type=Path)
    build_p.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        help="Directory for converted output (default: beside the source).",
    )
    build_p.add_argument("--force", action="store_true", help="Replace existing output.")
    build_p.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not create a transfer tar.gz for RPG Maker/Godot. Ren'Py still emits ZIP.",
    )
    build_p.add_argument(
        "--runtime",
        type=Path,
        help="Optional extracted ARM64 runtime override for RPG Maker/Godot backends.",
    )
    build_p.add_argument(
        "--nwjs-version",
        default=DEFAULT_NWJS_VERSION,
        help=f"NW.js version for RPG Maker MV/MZ (default: {DEFAULT_NWJS_VERSION}).",
    )
    build_p.add_argument(
        "--renpy-version",
        help="Override detected Ren'Py version when manual review says it is necessary.",
    )
    build_p.add_argument(
        "--full-renpy-archive",
        action="store_true",
        help="Include the complete Ren'Py distribution in the emitted ZIP.",
    )
    build_p.add_argument("--json", action="store_true", help="Print build result as JSON.")

    sub.add_parser("gui", help=f"Open {APP_NAME}.")
    sub.add_parser("backends", help="Show the currently integrated engine backends.")
    return parser


def _print_inspection(info) -> None:
    print(f"Source:         {info.source_path}")
    print(f"Engine:         {info.engine}")
    print(f"Family:         {info.family}")
    print(f"Backend:        {info.backend.value}")
    print(f"Version:        {info.engine_version or 'unknown'}")
    print(f"Runtime:        {info.runtime or 'automatic'}")
    print(f"Confidence:     {info.confidence}")
    print(f"Compatibility:  {info.compatibility}")
    print(f"Buildable:      {'yes' if info.buildable else 'no'}")
    if info.game_name:
        print(f"Game:           {info.game_name}")
    if info.evidence:
        print("Evidence:")
        for item in info.evidence:
            print(f"  - {item}")
    if info.warnings:
        print("Warnings:")
        for item in info.warnings:
            print(f"  - {item}")


def _print_build(result) -> None:
    print(f"Built:          {result.output_path}")
    print(f"Engine:         {result.engine}")
    print(f"Backend:        {result.backend.value}")
    if result.engine_version:
        print(f"Version:        {result.engine_version}")
    if result.build_directory:
        print(f"Build dir:      {result.build_directory}")
    if result.archive_path:
        print(f"Archive:        {result.archive_path}")
    if result.launcher_path:
        print(f"Launcher:       {result.launcher_path}")
    if result.runtime_path:
        print(f"Runtime:        {result.runtime_path}")
    if result.runtime_architecture:
        print(f"Runtime arch:   {result.runtime_architecture}")
    if result.warnings:
        print("Warnings:")
        for item in result.warnings:
            print(f"  - {item}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "inspect":
        info = inspect_source(args.path)
        if args.json:
            print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
        else:
            _print_inspection(info)
        return 0 if info.recognized else 2

    if args.command == "build":
        try:
            result = build_game(
                args.path,
                output_dir=args.output_dir,
                force=args.force,
                archive=not args.no_archive,
                runtime=args.runtime,
                nwjs_runtime_version=args.nwjs_version,
                renpy_version_override=args.renpy_version,
                full_renpy_archive=args.full_renpy_archive,
                progress=lambda stage, fraction, detail: print(
                    f"{stage}"
                    + (f" [{fraction * 100:5.1f}%]" if fraction is not None else "")
                    + (f": {detail}" if detail else ""),
                    file=sys.stderr,
                ),
                log=lambda message: print(message, file=sys.stderr),
            )
        except BuildError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            _print_build(result)
        return 0

    if args.command == "gui":
        from .gui import main as gui_main
        gui_main()
        return 0

    if args.command == "backends":
        print(APP_NAME)
        print("  Ren'Py 7/8 + selected legacy profiles -> RenFrame sdkarm backend")
        print("  RPG Maker XP/VX/VX Ace              -> mkxp-z ARM64")
        print("  RPG Maker MV/MZ                     -> NW.js ARM64")
        print("  Godot                                -> matching official Godot ARM64")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
