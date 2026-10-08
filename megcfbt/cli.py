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
        help="optional manually supplied ARM64 runtime for RPG Maker/Godot",
    )
    build_cmd.add_argument("--runtime-version", default=None)
    build_cmd.add_argument("--force", action="store_true")
    build_cmd.add_argument("--archive", action="store_true", help="create Frame-ready ZIP (default)")
    build_cmd.add_argument(
        "--no-archive",
        action="store_true",
        help="do not create the FrameDrop/Frame Control compatible ZIP package",
    )
    build_cmd.add_argument(
        "--steam-cover",
        type=Path,
        help="optional PNG/JPEG portrait artwork to bundle for Steam",
    )
    build_cmd.add_argument(
        "--add-to-steam",
        action="store_true",
        help="after conversion, add the build directly to local Steam (Linux ARM64 only)",
    )
    build_cmd.add_argument("--allow-renpy-version-mismatch", action="store_true")

    steam_cmd = sub.add_parser(
        "steam-install",
        help="add an existing converted build to local Steam on Linux ARM64",
    )
    steam_cmd.add_argument("build", type=Path)

    frame_control_cmd = sub.add_parser(
        "frame-control-limit",
        help="inspect, patch, or restore Frame Control's local upload-size guard",
    )
    frame_control_cmd.add_argument(
        "action",
        choices=("status", "patch", "restore"),
        nargs="?",
        default="status",
    )
    frame_control_cmd.add_argument(
        "--path",
        type=Path,
        help="Frame Control server.py, Frame Control.exe, or install directory",
    )

    sub.add_parser("gui", help="open the desktop frontend")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "gui":
        from megcfbt.gui import main as gui_main
        gui_main()
        return 0

    try:
        if args.command == "frame-control-limit":
            from megcfbt.frame_control_patch import (
                FrameControlPatchError,
                inspect_frame_control,
                patch_upload_limit,
                restore_upload_limit,
            )

            try:
                if args.action == "patch":
                    status = patch_upload_limit(args.path)
                elif args.action == "restore":
                    status = restore_upload_limit(args.path)
                else:
                    status = inspect_frame_control(args.path)
            except FrameControlPatchError as exc:
                print(f"ERROR: {exc}")
                return 1

            state = (
                "patched"
                if status.is_patched
                else "stock"
                if status.is_stock
                else "custom"
            )
            print(f"Frame Control: {status.server_path}")
            print(f"Upload limit:  {status.limit_gib} GiB ({state})")
            print(f"Backup:        {status.backup_path if status.has_backup else 'none'}")
            if args.action in ("patch", "restore"):
                print("Restart Frame Control before using the changed limit.")
            return 0

        if args.command == "steam-install":
            from megcfbt.steam_install import install_build

            installed = install_build(args.build, progress=print)
            print(f"Steam:   {installed['name']} ({installed['id']})")
            print(f"Path:    {installed['directory']}")
            for warning in installed["warnings"]:
                print(f"Warning: {warning}")
            return 0

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
            steam_cover=args.steam_cover,
            allow_renpy_version_mismatch=args.allow_renpy_version_mismatch,
            progress=print,
            **kwargs,
        )
        print(f"Built:   {result.output_path}")
        if result.archive_path:
            print(f"Package: {result.archive_path}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
        if args.add_to_steam:
            from megcfbt.steam_install import install_build

            installed = install_build(result.output_path, progress=print)
            print(f"Steam:   {installed['name']} ({installed['id']})")
            for warning in installed["warnings"]:
                print(f"Warning: {warning}")
        return 0
    except (ConversionError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
