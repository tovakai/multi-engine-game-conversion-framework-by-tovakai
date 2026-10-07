"""RenFrame command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from renframe import __version__
from renframe.builder import BuildError, build_game
from renframe.models import Compatibility
from renframe.report import (
    format_build_json,
    format_build_report,
    format_human_report,
    format_json_report,
)
from renframe.inspect_service import inspect_game

# Exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_GAME = 2
EXIT_COMPATIBILITY = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renframe",
        description=(
            "RenFrame inspects Ren'Py games and builds native Linux ARM64 "
            "(Steam Frame) directories by swapping in an ARM Ren'Py runtime."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser(
        "inspect",
        help="Inspect a Ren'Py game directory and print a compatibility report",
    )
    inspect_p.add_argument(
        "directory",
        type=Path,
        help="Path to the Ren'Py game directory",
    )
    inspect_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human report",
    )

    build_p = sub.add_parser(
        "build",
        help=(
            "Build a self-contained ARM64 Ren'Py game directory from a "
            "supplied ARM runtime"
        ),
    )
    build_p.add_argument("directory", type=Path, help="Path to the source game")
    build_p.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help="Path to an ARM64 Ren'Py SDK/runtime (required; no auto-download yet)",
    )
    build_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output directory (default: <source-parent>/<source-name>-frame)"
        ),
    )
    build_p.add_argument(
        "--force",
        action="store_true",
        help="Replace the output directory if it already exists",
    )
    build_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate source/runtime/paths only; copy nothing",
    )
    build_p.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Allow Ren'Py generation mismatches (strong warning)",
    )
    build_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human build report",
    )

    return parser


def _exit_for_compatibility(compat: Compatibility) -> int:
    if compat == Compatibility.LIKELY_COMPATIBLE:
        return EXIT_OK
    if compat == Compatibility.NOT_A_RENPY_GAME:
        return EXIT_INVALID_GAME
    if compat in {
        Compatibility.INCOMPATIBLE_NATIVE_CODE,
        Compatibility.UNKNOWN_RENPY_VERSION,
        Compatibility.NEEDS_TESTING,
    }:
        return EXIT_COMPATIBILITY
    return EXIT_ERROR


def cmd_inspect(directory: Path, *, as_json: bool) -> int:
    inspection = inspect_game(directory)
    if as_json:
        sys.stdout.write(format_json_report(inspection))
    else:
        sys.stdout.write(format_human_report(inspection))
    return _exit_for_compatibility(inspection.compatibility)


def cmd_build(
    directory: Path,
    *,
    output: Path | None,
    runtime: Path | None,
    force: bool,
    dry_run: bool,
    allow_version_mismatch: bool,
    as_json: bool,
) -> int:
    try:
        result = build_game(
            directory,
            output=output,
            runtime=runtime,
            force=force,
            dry_run=dry_run,
            allow_version_mismatch=allow_version_mismatch,
        )
    except BuildError as exc:
        message = str(exc)
        print(f"error: {message}", file=sys.stderr)
        lower = message.lower()
        if "not a ren'py game" in lower or "not a renpy game" in lower:
            return EXIT_INVALID_GAME
        if "incompatible" in lower:
            return EXIT_COMPATIBILITY
        return EXIT_ERROR
    except Exception as exc:  # pragma: no cover - unexpected failures
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if as_json:
        sys.stdout.write(format_build_json(result))
    else:
        sys.stdout.write(format_build_report(result))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return cmd_inspect(args.directory, as_json=args.json)
    if args.command == "build":
        return cmd_build(
            args.directory,
            output=args.output,
            runtime=args.runtime,
            force=args.force,
            dry_run=args.dry_run,
            allow_version_mismatch=args.allow_version_mismatch,
            as_json=args.json,
        )
    parser.error(f"Unknown command: {args.command}")
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
