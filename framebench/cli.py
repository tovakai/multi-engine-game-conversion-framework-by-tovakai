"""FrameBench command line. Kept for debugging and automation; the GUI is the Frame session UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from framebench import APP_NAME, STARDEW_APPID, __version__
from framebench import catalog
from framebench import compare as compare_mod
from framebench import protocol
from framebench import report as report_mod
from framebench import sensors
from framebench import session
from framebench import switch


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="framebench", description=f"{APP_NAME} native-versus-emulated Frame benchmarks")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect-sensors", help="discover read-only power and battery sensors")
    detect.add_argument("--sys-root", type=Path)
    detect.add_argument("--json", action="store_true")
    detect.set_defaults(func=_detect)

    games = sub.add_parser("list-games", help="list installed Steam games and converted packages")
    games.add_argument("--package", type=Path, action="append")
    games.add_argument("--json", action="store_true")
    games.set_defaults(func=_games)

    start = sub.add_parser("start", help="switch, launch, verify and record one variant")
    start.add_argument("--appid", type=int, default=STARDEW_APPID)
    start.add_argument("--mode", choices=("native", "original"), required=True)
    start.add_argument("--package", type=Path, required=True)
    start.add_argument("--name", default="")
    start.add_argument("--warmup", type=float, default=15.0)
    start.add_argument("--duration", type=float, default=180.0)
    start.add_argument("--interval", type=float, default=1.0)
    start.add_argument("--sys-root", type=Path)
    start.add_argument("--consent", action="store_true")
    start.add_argument("--simulated", action="store_true")
    start.add_argument("--json", action="store_true")
    start.set_defaults(func=_start)

    recover = sub.add_parser("recover", help="restore a leftover switch journal")
    recover.add_argument("--consent", action="store_true")
    recover.set_defaults(func=_recover)

    restore = sub.add_parser("restore", help="restore the user's normal Steam launch configuration")
    restore.add_argument("--consent", action="store_true")
    restore.set_defaults(func=_restore)

    compare = sub.add_parser("compare", help="compare two saved run JSON files")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.set_defaults(func=_compare)

    report = sub.add_parser("report", help="write an HTML report from one or more run JSON files")
    report.add_argument("runs", nargs="+", type=Path)
    report.add_argument("-o", "--output", type=Path, required=True)
    report.add_argument("--open", action="store_true")
    report.set_defaults(func=_report)

    proto = sub.add_parser("protocol", help="print or run the Stardew reference protocol")
    proto.add_argument("title", choices=("stardew",), default="stardew", nargs="?")
    proto.add_argument("--package", type=Path)
    proto.add_argument("--run", action="store_true")
    proto.add_argument("--consent", action="store_true")
    proto.add_argument("--simulated", action="store_true")
    proto.add_argument("--sys-root", type=Path)
    proto.add_argument("--warmup", type=float)
    proto.add_argument("--duration", type=float)
    proto.add_argument("-o", "--output", type=Path)
    proto.set_defaults(func=_protocol)

    gui = sub.add_parser("gui", help="open the FrameBench GUI")
    gui.set_defaults(func=_gui)
    return parser


def _detect(args) -> int:
    found = sensors.discover(args.sys_root)
    if args.json:
        print(json.dumps(found.as_dict(), indent=2))
        return 0
    print(f"sysfs root: {found.sys_root}")
    if not found.channels and found.battery is None:
        print("No Frame power sensors found. This host is not a Steam Frame, or sysfs is unavailable.")
    for channel in found.channels:
        print(f"{channel.role:7} {channel.label:8} {channel.device}")
    if found.battery:
        reading = found.battery.read()
        print(
            f"battery {reading.name} {reading.discharge_w} W charging={reading.charging} "
            f"capacity={reading.usable_capacity_wh} Wh ({reading.capacity_source})"
        )
    for warning in found.warnings:
        print("warning:", warning)
    return 0


def _games(args) -> int:
    entries = catalog.discover(extra_packages=args.package or [])
    if args.json:
        print(json.dumps([entry.as_dict() for entry in entries], indent=2))
        return 0
    for entry in entries:
        mark = "package" if entry.package else "steam-only"
        print(f"{entry.appid:8}  {entry.name}  [{mark}]")
    return 0


def _start(args) -> int:
    record = session.run_once(
        appid=args.appid,
        mode=args.mode,
        package=args.package,
        name=args.name,
        warmup_s=args.warmup,
        duration_s=args.duration,
        interval_s=args.interval,
        sys_root=args.sys_root,
        consent=args.consent,
        simulated=args.simulated or args.sys_root is not None,
    )
    payload = record.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"saved {record.id} mode={record.mode} verified={payload['verification']['matched']}")
        if payload["warnings"]:
            print("warnings:")
            for warning in payload["warnings"]:
                print(" -", warning)
    return 0 if payload["verification"]["matched"] else 3


def _recover(args) -> int:
    if not args.consent:
        print("Pass --consent to restore a leftover Steam launch transaction.", file=sys.stderr)
        return 2
    print(json.dumps(switch.recover(), indent=2))
    return 0


def _restore(args) -> int:
    if not args.consent:
        print("Pass --consent to restore Steam launch options.", file=sys.stderr)
        return 2
    print(json.dumps(switch.restore(), indent=2))
    return 0


def _compare(args) -> int:
    left = session.load_run(args.left)
    right = session.load_run(args.right)
    print(json.dumps(compare_mod.compare_runs(left, right), indent=2))
    return 0


def _report(args) -> int:
    runs = [session.load_run(path) for path in args.runs]
    path = report_mod.write_report(runs, args.output)
    print(path)
    if args.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def _protocol(args) -> int:
    if not args.run:
        print(protocol.describe())
        return 0
    if args.package is None:
        print("protocol --run requires --package", file=sys.stderr)
        return 2
    result = protocol.run_pair(
        args.package,
        sys_root=args.sys_root,
        consent=args.consent,
        simulated=args.simulated or args.sys_root is not None,
        warmup_s=args.warmup,
        duration_s=args.duration,
        report_path=args.output,
    )
    print(json.dumps({"protocol": result["protocol"], "comparison": result["comparison"], "report": result["report"]}, indent=2))
    return 0 if result["comparison"].get("comparable") else 3


def _gui(args) -> int:
    from framebench.gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
