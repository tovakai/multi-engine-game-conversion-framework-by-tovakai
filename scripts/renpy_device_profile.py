"""Launch an isolated Ren'Py copy and correlate runtime traces with Linux I/O.

Run on the Frame from its desktop terminal (Python 3). Install diagnostics.rpy
in the converted COPY first. --savedir must point to a COPY of your saves.
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def snapshot(pid):
    result = {"type": "process", "wall_time": time.time(), "pid": pid}
    for name in ("io", "status", "wchan", "stat"):
        try:
            result[name] = Path("/proc", str(pid), name).read_text()
        except OSError:
            pass
    for category in ("io", "memory", "cpu"):
        try:
            result["pressure_" + category] = Path("/proc/pressure", category).read_text()
        except OSError:
            pass
    for device in ("mmcblk0", "sda"):
        try:
            result[device] = Path("/sys/block", device, "stat").read_text()
        except OSError:
            pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--savedir", type=Path, required=True)
    parser.add_argument("--renderer", choices=("gl", "gl2"))
    parser.add_argument("--observe-only", action="store_true", help="Disable runtime hooks for baseline/overhead comparison")
    parser.add_argument("--strace", action="store_true", help="Separate high-overhead syscall evidence run")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    savedir = args.savedir.resolve()
    launcher = root / "renpy.sh"
    if not launcher.is_file():
        parser.error("Root must be a converted copy containing renpy.sh")
    if not savedir.is_dir():
        parser.error("Create a separate save-directory copy before profiling")
    if savedir.parent == Path.home() / ".renpy":
        parser.error("Do not profile with the original save directory; copy it first")
    output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = [output, Path(str(output) + ".process.jsonl"), Path(str(output) + ".syscalls.txt")]
    if any(path.exists() for path in artifacts):
        parser.error("Choose a new output filename; existing evidence is never overwritten")
    env = os.environ.copy()
    env["RENFRAME_DIAGNOSTICS"] = "0" if args.observe_only else "1"
    env["RENFRAME_TRACE"] = str(output)
    if args.renderer:
        env["RENPY_RENDERER"] = args.renderer
    command = ["bash", str(launcher), str(root), "--savedir", str(savedir)]
    if args.strace:
        command = ["strace", "-f", "-ttt", "-T", "-yy", "-e",
                   "trace=read,pread64,lseek,openat,newfstatat,mmap,ioctl,poll,ppoll,futex",
                   "-e", "raw=read,pread64", "-o", str(artifacts[2])] + command
    process = subprocess.Popen(command, env=env)
    print("Trace:", output, "PID:", process.pid, flush=True)
    with artifacts[1].open("x") as stream:
        stream.write(json.dumps({"type": "run", "wall_time": time.time(), "root": str(root),
                                 "observe_only": args.observe_only, "strace": args.strace,
                                 "note": "strace runs sample supervisor PID, not game PID" if args.strace else "exec launcher keeps game PID"}) + "\n")
        try:
            while process.poll() is None:
                stream.write(json.dumps(snapshot(process.pid)) + "\n")
                stream.flush()
                time.sleep(0.5)
        except KeyboardInterrupt:
            # Normal desktop Ctrl-C also reaches the child; allow clean shutdown.
            if process.poll() is None:
                process.send_signal(2)
            process.wait()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
