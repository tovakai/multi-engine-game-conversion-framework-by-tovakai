"""Minimal Frame-side FrameBench GUI. Ordinary sessions do not need a keyboard."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import time
import webbrowser
from typing import Any

from framebench import APP_NAME, STARDEW_APPID
from framebench import catalog
from framebench import compare as compare_mod
from framebench import paths
from framebench import report as report_mod
from framebench import sensors
from framebench import session
from framebench import switch

C_BG = "#05070b"
C_PANEL = "#101722"
C_PANEL_2 = "#172232"
C_PANEL_3 = "#0b1119"
C_BORDER = "#29485a"
C_TEXT = "#f1e8d8"
C_MUTED = "#9babb3"
C_ACCENT = "#ff8452"
C_ACCENT_HOVER = "#ff9a73"
C_TEAL = "#49d3c6"
C_OK = "#70d995"
C_ERR = "#ff667c"
C_WARN = "#ffb86c"

ctk: Any = None
tk: Any = None


def _load() -> None:
    global ctk, tk
    if ctk is not None:
        return
    try:
        import tkinter as _tk
        import customtkinter as _ctk
    except ImportError as exc:
        raise SystemExit('Missing GUI dependencies. Install with: pip install -e ".[gui]"') from exc
    tk = _tk
    ctk = _ctk


def live_readout(sys_root: Path | str | None = None) -> dict:
    found = sensors.discover(sys_root)
    battery = found.battery.read() if found.battery else None
    system = None
    if found.system:
        try:
            system = found.system[0].read_watts()
        except (OSError, ValueError):
            system = None
    return {
        "system_w": system,
        "battery_w": None if battery is None else battery.discharge_w,
        "battery_pct": None if battery is None else battery.capacity_pct,
        "charging": bool(battery.charging) if battery else False,
        "warnings": list(found.warnings),
    }


class FrameBenchApp:
    def __init__(self) -> None:
        _load()
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title(APP_NAME)
        self.root.geometry("980x720")
        self.root.minsize(860, 640)
        self.root.configure(fg_color=C_BG)
        self.entries: list[catalog.CatalogEntry] = []
        self.selected: catalog.CatalogEntry | None = None
        self.mode = "native"
        self.busy = False
        self.active: session.Session | None = None
        self.runs: list[dict] = []
        self.report_path: Path | None = None
        self.queue: queue.Queue = queue.Queue()
        self.started_mono = None
        self._build()
        self.refresh_games()
        self.root.after(200, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        ctk.CTkFrame(self.root, fg_color=C_ACCENT, height=3, corner_radius=0).pack(fill="x")
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(16, 8))
        ctk.CTkLabel(header, text=APP_NAME, font=ctk.CTkFont(size=26, weight="bold"), text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="NATIVE ARM64  vs  ORIGINAL STEAM / FEX   //   BATTERY FIRST",
            font=ctk.CTkFont(family="Courier", size=13, weight="bold"),
            text_color=C_TEAL,
        ).pack(anchor="w")

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=8)
        left = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=12, width=360)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        ctk.CTkLabel(left, text="STEAM GAME", text_color=C_TEAL, font=ctk.CTkFont(family="Courier", size=13, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4)
        )
        self.game_box = ctk.CTkComboBox(left, values=["No converted Steam games found"], height=42, command=self._pick)
        self.game_box.pack(fill="x", padx=16, pady=(0, 10))
        modes = ctk.CTkFrame(left, fg_color="transparent")
        modes.pack(fill="x", padx=16, pady=6)
        self.native_btn = ctk.CTkButton(modes, text="NATIVE ARM64", height=48, command=lambda: self._set_mode("native"))
        self.native_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.original_btn = ctk.CTkButton(modes, text="ORIGINAL STEAM", height=48, command=lambda: self._set_mode("original"))
        self.original_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))
        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=10)
        self.start_btn = ctk.CTkButton(
            actions, text="START BENCHMARK", height=52, fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            text_color="#1a0f0a", font=ctk.CTkFont(size=16, weight="bold"), command=self._start,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.stop_btn = ctk.CTkButton(actions, text="STOP", height=52, fg_color=C_PANEL_2, command=self._stop)
        self.stop_btn.pack(side="left", fill="x", padx=(6, 0), ipadx=18)
        extras = ctk.CTkFrame(left, fg_color="transparent")
        extras.pack(fill="x", padx=16)
        ctk.CTkButton(extras, text="REFRESH GAMES", height=40, fg_color=C_PANEL_2, command=self.refresh_games).pack(
            side="left", expand=True, fill="x", padx=(0, 6)
        )
        ctk.CTkButton(extras, text="OPEN REPORT", height=40, fg_color=C_PANEL_2, command=self._open_report).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )
        self.log = ctk.CTkTextbox(left, fg_color=C_PANEL_3, text_color=C_TEXT, height=220)
        self.log.pack(fill="both", expand=True, padx=16, pady=14)

        self.power = ctk.CTkLabel(right, text="SYSTEM\n— W", font=ctk.CTkFont(size=28, weight="bold"), text_color=C_TEAL)
        self.power.pack(pady=(22, 8))
        self.battery = ctk.CTkLabel(right, text="BATTERY\n— W", font=ctk.CTkFont(size=22, weight="bold"), text_color=C_TEXT)
        self.battery.pack(pady=4)
        self.elapsed = ctk.CTkLabel(right, text="00:00", font=ctk.CTkFont(size=20), text_color=C_MUTED)
        self.elapsed.pack(pady=8)
        self.verify = ctk.CTkLabel(right, text="MODE // idle", text_color=C_MUTED, wraplength=300)
        self.verify.pack(padx=16, pady=8)
        self.compare = ctk.CTkTextbox(right, fg_color=C_PANEL_3, text_color=C_TEXT, height=180)
        self.compare.pack(fill="both", expand=True, padx=14, pady=14)
        self._paint_mode()

    def refresh_games(self) -> None:
        self.entries = catalog.benchmarkable(catalog.discover())
        if not self.entries:
            self.game_box.configure(values=["No converted Steam games found"])
            self.selected = None
            return
        labels = [f"{entry.name}  ({entry.appid})" for entry in self.entries]
        self.game_box.configure(values=labels)
        self.game_box.set(labels[0])
        self.selected = self.entries[0]

    def _pick(self, value: str) -> None:
        for entry in self.entries:
            if f"{entry.name}  ({entry.appid})" == value:
                self.selected = entry
                return

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self._paint_mode()

    def _paint_mode(self) -> None:
        if self.mode == "native":
            self.native_btn.configure(fg_color=C_TEAL, text_color="#04120f")
            self.original_btn.configure(fg_color=C_PANEL_2, text_color=C_TEXT)
        else:
            self.original_btn.configure(fg_color=C_ACCENT, text_color="#1a0f0a")
            self.native_btn.configure(fg_color=C_PANEL_2, text_color=C_TEXT)

    def _log(self, message: str) -> None:
        self.log.insert("end", message + "\n")
        self.log.see("end")

    def _start(self) -> None:
        if self.busy:
            return
        if self.selected is None or self.selected.package is None:
            self._log("Select an installed Steam game that has a converted package.")
            return
        self.busy = True
        self.started_mono = time.monotonic()
        self._log(f"Starting {self.mode} benchmark for {self.selected.name} ({self.selected.appid})")
        thread = threading.Thread(target=self._run_session, daemon=True)
        thread.start()

    def _run_session(self) -> None:
        try:
            switch.recover(running_check=lambda _appid: False)
        except Exception as exc:
            self.queue.put(("log", f"Recovery note: {exc}"))
        try:
            record = session.run_once(
                appid=self.selected.appid if self.selected else STARDEW_APPID,
                mode=self.mode,
                package=self.selected.package if self.selected else Path("."),
                name=self.selected.name if self.selected else "",
                consent=True,
                warmup_s=15,
                duration_s=180,
            )
            self.queue.put(("done", record.as_dict()))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _stop(self) -> None:
        self.queue.put(("log", "Stop requested. The current sample loop will end and launch options will be restored."))
        # Session.stop is cooperative via duration; recover journal if a run is mid-switch.
        try:
            switch.restore(running_check=lambda _appid: False)
        except Exception as exc:
            self.queue.put(("log", f"Restore: {exc}"))

    def _open_report(self) -> None:
        if self.report_path and self.report_path.is_file():
            webbrowser.open(self.report_path.resolve().as_uri())
            return
        self._log("No report yet. Complete native and original runs first.")

    def _tick(self) -> None:
        try:
            readout = live_readout()
            sys_w = readout["system_w"]
            bat_w = readout["battery_w"]
            pct = readout["battery_pct"]
            self.power.configure(text=f"SYSTEM\n{sys_w:.2f} W" if sys_w is not None else "SYSTEM\n— W")
            charge = "  CHARGING" if readout["charging"] else ""
            battery_txt = f"BATTERY\n{bat_w:.2f} W{charge}" if bat_w is not None else f"BATTERY\n— W{charge}"
            if pct is not None:
                battery_txt += f"\n{pct}%"
            self.battery.configure(text=battery_txt, text_color=C_WARN if readout["charging"] else C_TEXT)
        except Exception:
            pass
        if self.started_mono and self.busy:
            elapsed = int(time.monotonic() - self.started_mono)
            self.elapsed.configure(text=f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(str(payload))
            elif kind == "error":
                self.busy = False
                self.verify.configure(text="MODE // failed", text_color=C_ERR)
                self._log(str(payload))
            elif kind == "done":
                self.busy = False
                self.runs.append(payload)
                verified = payload.get("verification", {}).get("matched")
                self.verify.configure(
                    text=f"MODE // {payload.get('mode')}  {'VERIFIED' if verified else 'UNVERIFIED'}",
                    text_color=C_OK if verified else C_ERR,
                )
                self._log(f"Finished {payload.get('id')}  verified={verified}")
                self._refresh_compare()
        self.root.after(500, self._tick)

    def _refresh_compare(self) -> None:
        native = next((run for run in reversed(self.runs) if run.get("mode") == "native"), None)
        original = next((run for run in reversed(self.runs) if run.get("mode") == "original"), None)
        self.compare.delete("1.0", "end")
        if not native or not original:
            self.compare.insert("end", "Complete one native and one original run to compare battery life.")
            return
        result = compare_mod.compare_runs(native, original)
        improvement = result.get("battery_life_improvement") or {}
        self.compare.insert("end", (improvement.get("label") or "No comparison") + "\n\n")
        for reason in result.get("reasons") or []:
            self.compare.insert("end", f"- {reason}\n")
        destination = paths.runs_dir() / "last-report.html"
        self.report_path = report_mod.write_report([native, original], destination, comparison=result)

    def _close(self) -> None:
        try:
            switch.restore(running_check=lambda _appid: False)
        except Exception:
            pass
        self.root.destroy()

    def mainloop(self) -> None:
        self.root.mainloop()


def main() -> None:
    FrameBenchApp().mainloop()
