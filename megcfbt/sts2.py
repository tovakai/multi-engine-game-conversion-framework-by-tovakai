"""Framework adapter for the isolated, source-building STS2 backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig

from megcfbt.models import UnifiedInspection


def tools_directory() -> Path:
    candidates = [Path(__file__).resolve().parents[1] / "experiments/sts2-steamworks",
                  Path(getattr(sys, "_MEIPASS", sys.prefix)) / "sts2-tools",
                  Path(sysconfig.get_path("data")) / "share/megcfbt/sts2"]
    for path in candidates:
        if (path / "pipeline.py").is_file():
            return path
    raise RuntimeError("STS2 backend tools are missing from this installation")


def python_command() -> str:
    if getattr(sys, "frozen", False):
        python = shutil.which("python3") or shutil.which("python")
        if not python:
            raise RuntimeError("STS2 source builds require Python 3.10+ on the build host")
        return python
    return sys.executable


def available(sdk: Path | str | None = None) -> bool:
    sdk = sdk or os.environ.get("MEGCFBT_STS2_FMOD_SDK")
    return bool(platform.system() == "Linux" and platform.machine() in {"aarch64", "arm64"}
                and sdk and Path(sdk).exists()
                and shutil.which(os.environ.get("MEGCFBT_STS2_SCONS", "scons"))
                and all(shutil.which(t) for t in ("git", "g++", "readelf"))
                and Path("/opt/steamvr/bin/linuxarm64/libsteam_api.so").is_file())


def summary(root: Path) -> UnifiedInspection | None:
    if not (root / "SlayTheSpire2.pck").is_file() or not (root / "data_sts2_windows_x86_64/sts2.dll").is_file():
        return None
    try:
        from megcfbt.sts2_backend import module
        report = module("preflight").inspect_source(root, full=False)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        report = {"supported": False, "errors": [str(error)]}
    supported = bool(report.get("supported"))
    warnings = tuple(str(e) for e in report.get("errors", []))
    if supported:
        warnings += ("Source hashes will be verified before building. Device acceptance is still required.",
                     "Requires Linux AArch64 build tools, FMOD 2.03.15 SDK, applicable middleware licensing and Valve's installed ARM64 Steam API.")
    return UnifiedInspection(
        source_path=root, backend="sts2", engine="godot", engine_label="Slay the Spire 2 (Godot .NET)",
        engine_version="4.5.1" if supported else None, game_name="Slay the Spire 2",
        compatibility="needs_testing" if supported else "unsupported",
        confidence="high", runtime_kind="sts2-native-source", buildable=supported and available(),
        warnings=warnings, evidence=(f"STS2 {report.get('release')} / {report.get('commit')}",))


def build(source: Path, output: Path, *, sdk=None, progress=None):
    args = [python_command(), str(tools_directory() / "pipeline.py"), str(source), str(output)]
    if sdk:
        args += ["--fmod-sdk", str(sdk)]
    # Stream progress on stderr; JSON result is small and read after process exit.
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        assert process.stderr is not None
        for line in process.stderr:
            if progress:
                progress(line.rstrip())
        assert process.stdout is not None
        payload = process.stdout.read()
        code = process.wait()
    try:
        report = json.loads(payload)
    except ValueError as error:
        raise RuntimeError("STS2 pipeline returned invalid diagnostics: " + payload[-2000:]) from error
    if code or report.get("errors"):
        raise RuntimeError("STS2 conversion failed: " + str(report.get("errors", [f"exit {code}"])))
    return report
