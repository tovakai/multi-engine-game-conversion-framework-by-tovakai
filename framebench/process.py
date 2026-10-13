"""Read-only process, architecture and FEX/Proton ownership checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import time

ELF_MAGIC = b"\x7fELF"
EM_AARCH64 = 183
EM_X86_64 = 62
FEX_MARKERS = ("fex-compat-tool", "fexinterpreter", "/usr/bin/fex", "fex-emu", "fexbash")
PROTON_MARKERS = ("proton", "wine", "waitforexitandrun")
STEAM_ID_KEYS = ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID")


class ProcessError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    comm: str
    exe: str | None
    cmdline: list[str]
    elf_machine: str | None
    rss_bytes: int | None
    cpu_pct: float | None
    environ: dict[str, str]
    ancestry: list[str]
    fex: bool
    proton: bool
    native_aarch64: bool
    steam_appid: str | None

    def as_dict(self) -> dict:
        return {
            "pid": self.pid,
            "comm": self.comm,
            "exe": self.exe,
            "cmdline": list(self.cmdline),
            "elf_machine": self.elf_machine,
            "rss_bytes": self.rss_bytes,
            "cpu_pct": self.cpu_pct,
            "fex": self.fex,
            "proton": self.proton,
            "native_aarch64": self.native_aarch64,
            "steam_appid": self.steam_appid,
            "ancestry": list(self.ancestry),
        }


@dataclass
class Verification:
    requested_mode: str
    matched: bool
    reason: str
    snapshot: ProcessSnapshot | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "requested_mode": self.requested_mode,
            "matched": self.matched,
            "reason": self.reason,
            "snapshot": None if self.snapshot is None else self.snapshot.as_dict(),
            "warnings": list(self.warnings),
        }


def elf_machine(path: Path | str | None) -> str | None:
    if path is None:
        return None
    try:
        with Path(path).open("rb") as stream:
            header = stream.read(20)
    except OSError:
        return None
    if header[:4] != ELF_MAGIC or len(header) < 20:
        return None
    machine = int.from_bytes(header[18:20], "little")
    if machine == EM_AARCH64:
        return "aarch64"
    if machine == EM_X86_64:
        return "x86_64"
    return f"unknown-{machine}"


def parse_environ(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        try:
            values[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
        except Exception:
            continue
    return values


def parse_cmdline(raw: bytes) -> list[str]:
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _looks_like(markers: tuple[str, ...], *texts: str) -> bool:
    blob = " ".join(texts).casefold()
    return any(marker in blob for marker in markers)


def snapshot_pid(pid: int, proc_root: Path | str = "/proc") -> ProcessSnapshot | None:
    root = Path(proc_root) / str(pid)
    if not root.is_dir():
        return None
    comm = _read(root / "comm") or ""
    cmdline = parse_cmdline(_read_bytes(root / "cmdline"))
    environ = parse_environ(_read_bytes(root / "environ"))
    exe = _resolve_exe(root / "exe")
    machine = elf_machine(exe)
    rss = _rss_bytes(root / "status")
    ancestry = _ancestry(pid, proc_root)
    texts = [comm, exe or "", " ".join(cmdline), " ".join(ancestry)]
    steam_appid = next((environ[key] for key in STEAM_ID_KEYS if environ.get(key)), None)
    fex = _looks_like(FEX_MARKERS, *texts)
    proton = _looks_like(PROTON_MARKERS, *texts) and not fex
    return ProcessSnapshot(
        pid=pid,
        comm=comm.strip(),
        exe=exe,
        cmdline=cmdline,
        elf_machine=machine,
        rss_bytes=rss,
        cpu_pct=None,
        environ={key: environ[key] for key in STEAM_ID_KEYS if key in environ},
        ancestry=ancestry,
        fex=fex,
        proton=proton,
        native_aarch64=machine == "aarch64" and not fex and not proton,
        steam_appid=steam_appid,
    )


def find_game_processes(appid: int, proc_root: Path | str = "/proc") -> list[ProcessSnapshot]:
    found: list[ProcessSnapshot] = []
    root = Path(proc_root)
    if not root.is_dir():
        return found
    expected = str(int(appid))
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        snap = snapshot_pid(int(entry.name), proc_root)
        if snap is None:
            continue
        if snap.steam_appid == expected:
            found.append(snap)
            continue
        joined = " ".join(snap.cmdline).casefold()
        if expected in joined and "steam" in joined:
            found.append(snap)
    return found


def game_is_running(appid: int, proc_root: Path | str = "/proc") -> bool:
    return bool(find_game_processes(appid, proc_root))


def verify_mode(requested: str, processes: list[ProcessSnapshot]) -> Verification:
    if requested not in {"native", "original"}:
        return Verification(requested, False, f"Unknown mode {requested!r}")
    if not processes:
        return Verification(requested, False, "No Steam-owned game process was found for the requested AppID.")
    primary = _primary_process(processes)
    if requested == "native":
        if primary.native_aarch64:
            return Verification(requested, True, "Running process is a native AArch64 ELF without FEX or Proton.", primary)
        if primary.fex:
            return Verification(requested, False, "Requested native ARM64 but FEX is in the process chain.", primary)
        if primary.proton:
            return Verification(requested, False, "Requested native ARM64 but Proton/Wine is in the process chain.", primary)
        if primary.elf_machine == "x86_64":
            return Verification(requested, False, "Requested native ARM64 but the running ELF is x86_64.", primary)
        return Verification(
            requested,
            False,
            f"Could not confirm native AArch64 execution (machine={primary.elf_machine!r}).",
            primary,
        )
    if primary.fex or primary.elf_machine == "x86_64":
        return Verification(requested, True, "Running process matches original/emulated x86 execution.", primary)
    if primary.proton:
        return Verification(requested, True, "Running process matches original Proton/Windows execution.", primary)
    if primary.native_aarch64:
        return Verification(requested, False, "Requested original Steam/FEX but the process is native AArch64.", primary)
    return Verification(requested, False, "Could not confirm original/emulated execution.", primary)


class CpuMeter:
    def __init__(self, proc_root: Path | str = "/proc", *, clock=time.monotonic) -> None:
        self.proc_root = Path(proc_root)
        self.clock = clock
        self._previous: dict[int, tuple[float, float]] = {}
        self._system: tuple[float, float] | None = None

    def read(self, pid: int | None = None) -> dict:
        stat = _read((self.proc_root / "stat"))
        system_total = _system_jiffies(stat)
        now = self.clock()
        cpu_pct = None
        if self._system is not None and system_total is not None:
            dt = now - self._system[0]
            dj = system_total - self._system[1]
            if dt > 0 and dj >= 0:
                pass
        if system_total is not None:
            self._system = (now, system_total)
        rss = None
        mem_available = _meminfo_available(self.proc_root / "meminfo")
        if pid is not None:
            snap_stat = _read(self.proc_root / str(pid) / "stat")
            rss = _rss_bytes(self.proc_root / str(pid) / "status")
            process_total = _process_jiffies(snap_stat)
            previous = self._previous.get(pid)
            if previous and process_total is not None and system_total is not None:
                p_dt = process_total - previous[1]
                s_prev = self._system
                if s_prev:
                    s_dt = system_total - s_prev[1] if s_prev[1] <= system_total else 0
                    if s_dt > 0:
                        cpu_pct = max(0.0, min(100.0 * p_dt / s_dt, 400.0))
            if process_total is not None:
                self._previous[pid] = (now, process_total)
        return {"cpu_pct": cpu_pct, "rss_bytes": rss, "mem_available_bytes": mem_available}


def _primary_process(processes: list[ProcessSnapshot]) -> ProcessSnapshot:
    def score(item: ProcessSnapshot) -> tuple[int, int]:
        interesting = 1
        if item.comm.casefold() in {"steam", "steamwebhelper", "reaper", "pressure-vessel-wrap"}:
            interesting = 0
        return (interesting, item.rss_bytes or 0)

    return max(processes, key=score)


def _ancestry(pid: int, proc_root: Path | str) -> list[str]:
    names: list[str] = []
    current = pid
    seen: set[int] = set()
    root = Path(proc_root)
    for _ in range(12):
        if current in seen or current <= 1:
            break
        seen.add(current)
        stat = _read(root / str(current) / "stat")
        if not stat:
            break
        match = re.search(r"\((.*)\)\s+(\S+)\s+(\d+)", stat)
        if not match:
            break
        names.append(match.group(1))
        try:
            current = int(match.group(3))
        except ValueError:
            break
    return names


def _resolve_exe(link: Path) -> str | None:
    try:
        return str(link.resolve())
    except OSError:
        try:
            return str(link.readlink())
        except OSError:
            return None


def _rss_bytes(status: Path) -> int | None:
    text = _read(status)
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            try:
                return int(parts[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _system_jiffies(stat: str | None) -> float | None:
    if not stat:
        return None
    line = stat.splitlines()[0]
    parts = line.split()
    if len(parts) < 8 or parts[0] != "cpu":
        return None
    try:
        return sum(float(p) for p in parts[1:])
    except ValueError:
        return None


def _process_jiffies(stat: str | None) -> float | None:
    if not stat:
        return None
    match = re.search(r"\)\s+\S+\s+", stat)
    if not match:
        return None
    parts = stat[match.end():].split()
    # After comm, fields 12/13 (0-based 11/12 in this remainder? utime/stime are 14/15 overall)
    # stat format: pid (comm) state ppid ... utime stime at fields 14 and 15 (1-based).
    tokens = stat.split()
    # comm can contain spaces; find the last ')' then split the rest.
    close = stat.rfind(")")
    if close < 0:
        return None
    rest = stat[close + 1:].split()
    if len(rest) < 15:
        return None
    try:
        return float(rest[11]) + float(rest[12])
    except ValueError:
        return None


def _meminfo_available(path: Path) -> int | None:
    text = _read(path)
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            try:
                return int(parts[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""
