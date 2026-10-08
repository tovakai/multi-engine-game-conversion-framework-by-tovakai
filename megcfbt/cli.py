"""Command line interface for the entire absurdly named application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from megcfbt import APP_NAME
from megcfbt.router import ConversionError, build_source, inspect_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multi-engine-game-conversion-framework-by-tovakai")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inspect", help="detect engine and compatibility")
    inspect_cmd.add_argument("source", type=Path)
    inspect_cmd.add_argument("--json", action="store_true")

    build_cmd = sub.add_parser("build", help="convert a supported game to Linux ARM64")
    build_cmd.add_argument("source", type=Path)
    build_cmd.add_argument("-o", "--output", type=Path)
    build_cmd.add_argument(
        "--renpy-runtime",
        type=Path,
        help=(
            "manual Ren'Py ARM64 runtime override; exact detected Ren'Py 7/8 "
            "versions otherwise resolve automatically"
        ),
    )
    build_cmd.add_argument(
        "--runtime",
        type=Path,
        help=(
            "manual backend runtime override for RPG Maker/Godot; eligible "
            "Godot 3.7 custom + GodotSteam exports can build a compatibility "
            "runtime automatically on Linux ARM64"
        ),
    )
    build_cmd.add_argument("--runtime-version", default=None)
    build_cmd.add_argument("--force", action="store_true")
    build_cmd.add_argument("--no-archive", action="store_true")
    build_cmd.add_argument("--allow-renpy-version-mismatch", action="store_true")
    build_cmd.add_argument("--fmod-sdk", type=Path, help="Authorized FMOD Studio API 2.03.15 Linux SDK for STS2 source builds")
    build_cmd.add_argument("--acknowledge-licenses", action="store_true", help="Acknowledge game ownership and STS2 vendor dependency permissions")

    sub.add_parser("gui", help="open the desktop frontend")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "gui":
        from megcfbt.gui import main as gui_main
        gui_main()
        return 0

    try:
        if args.command == "inspect":
            result = inspect_source(args.source)
            payload = {
                "source_path": str(result.source_path),
                "backend": result.backend,
                "engine": result.engine,
                "engine_label": result.engine_label,
                "engine_version": result.engine_version,
                "game_name": result.game_name,
                "compatibility": result.compatibility,
                "confidence": result.confidence,
                "runtime_kind": result.runtime_kind,
                "buildable": result.buildable,
                "warnings": list(result.warnings),
                "evidence": list(result.evidence),
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(APP_NAME)
                print(f"Game:          {result.game_name or 'unknown'}")
                print(f"Engine:        {result.engine_label}" + (
                    f" {result.engine_version}" if result.engine_version else ""
                ))
                print(f"Backend:       {result.backend or 'none'}")
                print(f"Compatibility: {result.compatibility}")
                print(f"Confidence:    {result.confidence}")
                if result.runtime_kind:
                    print(f"Runtime:       {result.runtime_kind}")
                for warning in result.warnings:
                    print(f"Warning:       {warning}")
            return 0 if result.backend else 2

        kwargs = {}
        if args.runtime_version:
            kwargs["runtime_version"] = args.runtime_version
        result = build_source(
            args.source,
            output=args.output,
            renpy_runtime=args.renpy_runtime,
            backend_runtime=args.runtime,
            force=args.force,
            archive=not args.no_archive,
            allow_renpy_version_mismatch=args.allow_renpy_version_mismatch,
            progress=print,
            sts2_sdk=args.fmod_sdk,
            acknowledge_licenses=args.acknowledge_licenses,
            **kwargs,
        )
        print(f"Built:   {result.output_path}")
        if result.archive_path:
            print(f"Archive: {result.archive_path}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
        return 0
    except ConversionError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
