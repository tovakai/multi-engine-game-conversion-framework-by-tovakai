"""Desktop GUI for Multi-Engine Game Conversion Framework by tovakai."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from megcfbt import APP_NAME
from megcfbt.models import UnifiedBuildResult, UnifiedInspection
from megcfbt.router import (
    ConversionError,
    build_source,
    inspect_source,
    output_path_for_source,
)

APP_TAG = "CONVERSION DECK // Ren'Py · RPG Maker · Godot → Linux ARM64"

# Cassette-futurist palette: smoked plastic, phosphor teal, warm transport orange.
C_BG = "#05070b"
C_BG_2 = "#090e15"
C_PANEL = "#101722"
C_PANEL_2 = "#172232"
C_PANEL_3 = "#0b1119"
C_BORDER = "#29485a"
C_BORDER_GLOW = "#49d3c6"
C_TEXT = "#f1e8d8"
C_MUTED = "#9babb3"
C_DIM = "#657682"
C_ACCENT = "#ff8452"
C_ACCENT_HOVER = "#ff9a73"
C_TEAL = "#49d3c6"
C_TEAL_SOFT = "#2b8f89"
C_MAGENTA = "#d86df0"
C_OK = "#70d995"
C_ERR = "#ff667c"
C_WARN = "#ffb86c"

ctk: Any = None
tk: Any = None
filedialog: Any = None
messagebox: Any = None
DND_FILES: Any = None
TkinterDnD: Any = None
_HAS_DND = False


def _load_gui_dependencies() -> None:
    global ctk, tk, filedialog, messagebox, DND_FILES, TkinterDnD, _HAS_DND
    if ctk is not None:
        return
    try:
        import tkinter as _tk
        from tkinter import filedialog as _filedialog
        from tkinter import messagebox as _messagebox
        import customtkinter as _ctk
    except ImportError as exc:
        raise SystemExit(
            'Missing GUI dependencies. Install with: pip install -e ".[gui]"'
        ) from exc

    tk = _tk
    filedialog = _filedialog
    messagebox = _messagebox
    ctk = _ctk

    try:
        from tkinterdnd2 import DND_FILES as _DND_FILES
        from tkinterdnd2 import TkinterDnD as _TkinterDnD
        DND_FILES = _DND_FILES
        TkinterDnD = _TkinterDnD
        _HAS_DND = True
    except ImportError:
        _HAS_DND = False


def _make_root():
    _load_gui_dependencies()
    ctk.set_appearance_mode("dark")
    if _HAS_DND:
        class CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.TkdndVersion = TkinterDnD._require(self)
        root = CTkDnD()
    else:
        root = ctk.CTk()

    root.title(APP_NAME)
    root.geometry("1080x820")
    root.minsize(920, 720)
    root.configure(fg_color=C_BG)
    return root


def _open_path(path: Path) -> None:
    try:
        target = path.expanduser().resolve()
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except Exception:
        pass


class ConverterApp:
    def __init__(self) -> None:
        self.root = _make_root()
        self.source: Path | None = None
        self.inspection: UnifiedInspection | None = None
        self.renpy_runtime: Path | None = None
        self.last_output: Path | None = None
        self.last_archive: Path | None = None
        self.output_dir = Path.home() / "Desktop"
        if not self.output_dir.is_dir():
            self.output_dir = Path.home()

        self._busy = False
        self._generation = 0
        self._ui_queue: queue.Queue[Any] = queue.Queue()
        self.archive_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.after(25, self._drain_ui_queue)

    def _build_ui(self) -> None:
        ctk.CTkFrame(self.root, fg_color=C_ACCENT, height=3, corner_radius=0).pack(
            fill="x", side="top"
        )
        ctk.CTkFrame(self.root, fg_color=C_TEAL_SOFT, height=1, corner_radius=0).pack(
            fill="x", side="top"
        )

        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(18, 8))

        header_left = ctk.CTkFrame(header, fg_color="transparent")
        header_left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            header_left,
            text=APP_NAME,
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_left,
            text=APP_TAG,
            font=ctk.CTkFont(family="Courier", size=13, weight="bold"),
            text_color=C_TEAL,
        ).pack(anchor="w", pady=(4, 0))

        deck_badge = ctk.CTkFrame(
            header,
            fg_color=C_PANEL_3,
            border_width=1,
            border_color=C_BORDER,
            corner_radius=4,
        )
        deck_badge.pack(side="right", padx=(16, 0))
        ctk.CTkLabel(
            deck_badge,
            text="tovakai systems //\nFRAME CONVERSION UNIT // MK I",
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            text_color=C_MUTED,
            justify="right",
        ).pack(padx=10, pady=7)

        ctk.CTkFrame(
            self.root, fg_color=C_BORDER, height=1, corner_radius=0
        ).pack(fill="x", padx=28)

        self.drop = ctk.CTkFrame(
            self.root,
            fg_color=C_PANEL_3,
            border_width=2,
            border_color=C_BORDER_GLOW,
            corner_radius=8,
            height=132,
        )
        self.drop.pack(fill="x", padx=28, pady=14)
        self.drop.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop,
            text="INSERT GAME PAYLOAD",
            font=ctk.CTkFont(family="Courier", size=20, weight="bold"),
            text_color=C_TEXT,
        )
        self.drop_label.pack(expand=True, pady=(22, 2))
        self.path_label = ctk.CTkLabel(
            self.drop,
            text="DROP FOLDER OR .ZIP HERE  //  SOURCE REMAINS UNTOUCHED",
            font=ctk.CTkFont(size=13),
            text_color=C_MUTED,
        )
        self.path_label.pack(pady=(0, 16))

        if _HAS_DND:
            try:
                self.drop.drop_target_register(DND_FILES)
                self.drop.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        controls = ctk.CTkFrame(self.root, fg_color="transparent")
        controls.pack(fill="x", padx=28, pady=(0, 6))
        ctk.CTkButton(
            controls,
            text="BROWSE",
            width=120,
            height=40,
            fg_color=C_PANEL_2,
            hover_color=C_BORDER,
            command=self._browse,
        ).pack(side="left", padx=(0, 10))

        self.convert_btn = ctk.CTkButton(
            controls,
            text="CONVERT",
            state="disabled",
            width=168,
            height=40,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            text_color="#1a0f0a",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_convert,
        )
        self.convert_btn.pack(side="left")

        ctk.CTkButton(
            controls,
            text="OUTPUT FOLDER",
            width=132,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=C_BORDER,
            text_color=C_MUTED,
            command=self._pick_output,
        ).pack(side="right")
        ctk.CTkButton(
            controls,
            text="OPEN OUTPUT",
            width=120,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=C_BORDER,
            text_color=C_MUTED,
            command=self._open_output,
        ).pack(side="right", padx=(0, 8))

        options = ctk.CTkFrame(self.root, fg_color="transparent")
        options.pack(fill="x", padx=28, pady=(0, 8))
        ctk.CTkCheckBox(
            options,
            text="CREATE TRANSFER .TAR.GZ",
            variable=self.archive_var,
            fg_color=C_TEAL,
            text_color=C_MUTED,
        ).pack(side="left")
        ctk.CTkCheckBox(
            options,
            text="REPLACE EXISTING OUTPUT",
            variable=self.force_var,
            fg_color=C_ACCENT,
            text_color=C_MUTED,
        ).pack(side="left", padx=(18, 0))

        self.runtime_button = ctk.CTkButton(
            options,
            text="RUNTIME // AUTOMATIC",
            width=250,
            height=30,
            fg_color=C_PANEL_2,
            hover_color=C_BORDER,
            text_color=C_MUTED,
            state="disabled",
            command=self._pick_renpy_runtime,
        )
        self.runtime_button.pack(side="right")

        self.out_label = ctk.CTkLabel(
            self.root,
            text=f"OUTPUT // {self.output_dir}",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.out_label.pack(anchor="e", padx=28)

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=10)

        left = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(
            left, text="ACTIVITY LOG", text_color=C_TEAL,
            font=ctk.CTkFont(family="Courier", size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(14, 4))
        self.log_box = ctk.CTkTextbox(
            left, fg_color=C_PANEL_3, text_color=C_TEXT, corner_radius=6, wrap="word",
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family="Courier", size=12)
        )
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        right = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14, width=360)
        right.pack(side="right", fill="both", padx=(10, 0))
        right.pack_propagate(False)

        ctk.CTkLabel(
            right, text="DETECTED PAYLOAD", text_color=C_ACCENT,
            font=ctk.CTkFont(family="Courier", size=13, weight="bold")
        ).pack(anchor="w", padx=14, pady=(14, 8))
        self.game_label = ctk.CTkLabel(
            right, text="No game selected", text_color=C_TEXT,
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w", justify="left", wraplength=320
        )
        self.game_label.pack(fill="x", padx=14)
        self.engine_label = ctk.CTkLabel(
            right, text="Engine: —", text_color=C_MUTED, anchor="w"
        )
        self.engine_label.pack(fill="x", padx=14, pady=(8, 0))
        self.backend_label = ctk.CTkLabel(
            right, text="Backend: —", text_color=C_MUTED, anchor="w"
        )
        self.backend_label.pack(fill="x", padx=14, pady=(2, 0))
        self.compat_label = ctk.CTkLabel(
            right, text="Compatibility: —", text_color=C_MUTED,
            anchor="w", justify="left", wraplength=320
        )
        self.compat_label.pack(fill="x", padx=14, pady=(2, 10))

        self.notes_box = ctk.CTkTextbox(
            right, fg_color=C_PANEL_3, text_color=C_MUTED,
            corner_radius=6, wrap="word", border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family="Courier", size=11)
        )
        self.notes_box.pack(fill="both", expand=True, padx=12, pady=(2, 12))
        self.notes_box.insert(
            "1.0",
            "ROUTING MATRIX ONLINE.\n\n"
            "RenFrame and RPGMFrame remain focused backends. Engine detection "
            "selects the conversion path; source payloads stay untouched."
        )
        self.notes_box.configure(state="disabled")

        progress_panel = ctk.CTkFrame(self.root, fg_color="transparent")
        progress_panel.pack(fill="x", padx=28, pady=(0, 6))

        overall_row = ctk.CTkFrame(progress_panel, fg_color="transparent")
        overall_row.pack(fill="x")
        ctk.CTkLabel(
            overall_row,
            text="OVERALL",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")
        self.progress_percent_label = ctk.CTkLabel(
            overall_row,
            text="0%",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=11),
        )
        self.progress_percent_label.pack(side="right")

        self.overall_progress = ctk.CTkProgressBar(
            progress_panel,
            mode="determinate",
            fg_color=C_PANEL,
            progress_color=C_TEAL,
        )
        self.overall_progress.pack(fill="x", pady=(2, 6))
        self.overall_progress.set(0.0)

        self.activity_label = ctk.CTkLabel(
            progress_panel,
            text="CURRENT OPERATION // IDLE",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=11),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self.activity_label.pack(fill="x")
        self.activity_progress = ctk.CTkProgressBar(
            progress_panel,
            mode="indeterminate",
            fg_color=C_PANEL,
            progress_color=C_ACCENT,
        )
        self.activity_progress.pack(fill="x", pady=(2, 0))
        self.activity_progress.stop()
        status_row = ctk.CTkFrame(self.root, fg_color="transparent")
        status_row.pack(fill="x", padx=28, pady=(0, 14))
        self.status = ctk.CTkLabel(
            status_row,
            text="SYSTEM READY",
            text_color=C_MUTED,
            font=ctk.CTkFont(family="Courier", size=11, weight="bold"),
        )
        self.status.pack(side="left")
        ctk.CTkLabel(
            status_row,
            text="tovakai // ARM64 conversion deck",
            text_color=C_DIM,
            font=ctk.CTkFont(family="Courier", size=10),
        ).pack(side="right")

    def _dispatch(self, callback) -> None:
        if threading.current_thread() is threading.main_thread():
            callback()
        else:
            self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        try:
            self.root.after(25, self._drain_ui_queue)
        except Exception:
            pass

    def _log(self, message: str) -> None:
        self._dispatch(lambda: (self.log_box.insert("end", message + "\n"), self.log_box.see("end")))

    def _set_status(self, message: str, color: str = C_MUTED) -> None:
        self._dispatch(lambda: self.status.configure(text=message, text_color=color))

    def _set_progress(self, value: float, message: str) -> None:
        clamped = max(0.0, min(1.0, value))

        def update() -> None:
            self.overall_progress.set(clamped)
            self.progress_percent_label.configure(text=f"{round(clamped * 100)}%")
            self.activity_label.configure(text=f"CURRENT OPERATION // {message.upper()}")

        self._dispatch(update)

    def _progress_log(self, message: str) -> None:
        self._log(message)
        self._dispatch(
            lambda: self.activity_label.configure(text=f"CURRENT OPERATION // {message.upper()}")
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.convert_btn.configure(state="disabled", text="WORKING…")
            self.overall_progress.set(0.0)
            self.progress_percent_label.configure(text="0%")
            self.activity_label.configure(text="CURRENT OPERATION // STARTING CONVERSION…")
            self.activity_progress.start()
        else:
            allowed = bool(self.inspection and self.inspection.buildable)
            self.convert_btn.configure(state="normal" if allowed else "disabled", text="CONVERT")
            self.activity_progress.stop()

    def _set_source(self, path: Path) -> None:
        source = path.expanduser().resolve()
        if not source.exists():
            messagebox.showerror(APP_NAME, f"Path does not exist:\n{source}")
            return
        if source.is_file() and source.suffix.lower() != ".zip":
            messagebox.showinfo(APP_NAME, "Select a game folder or .zip archive.")
            return

        self.source = source
        self.inspection = None
        self.renpy_runtime = None
        self.convert_btn.configure(state="disabled")
        self.path_label.configure(text=str(source), text_color=C_TEAL)
        self.drop_label.configure(text="SCANNING PAYLOAD…")
        self.game_label.configure(text=source.stem if source.is_file() else source.name)
        self.engine_label.configure(text="Engine: inspecting…")
        self.backend_label.configure(text="Backend: inspecting…")
        self.compat_label.configure(text="Compatibility: checking…")
        self.overall_progress.set(0.0)
        self.progress_percent_label.configure(text="0%")
        self.activity_label.configure(text="CURRENT OPERATION // INSPECTING SOURCE…")
        self.activity_progress.start()
        self._generation += 1
        generation = self._generation

        def worker() -> None:
            try:
                result = inspect_source(source)
                self._dispatch(lambda: self._show_inspection(result) if generation == self._generation else None)
            except Exception as exc:
                self._dispatch(lambda: self._inspection_failed(str(exc)) if generation == self._generation else None)

        threading.Thread(target=worker, daemon=True).start()

    def _show_inspection(self, result: UnifiedInspection) -> None:
        self.activity_progress.stop()
        self.activity_label.configure(text="CURRENT OPERATION // READY")
        self.inspection = result
        version = f" {result.engine_version}" if result.engine_version else ""
        self.game_label.configure(text=result.game_name or "Unknown game")
        self.engine_label.configure(text=f"Engine: {result.engine_label}{version}", text_color=C_TEXT)
        self.backend_label.configure(text=f"Backend: {result.backend or 'none'}", text_color=C_MUTED)
        self.compat_label.configure(
            text=f"Compatibility: {result.compatibility}  ·  confidence {result.confidence}",
            text_color=C_OK if result.buildable else C_ERR,
        )

        if result.engine == "renpy":
            if self.renpy_runtime:
                runtime_text = f"Ren'Py override: {self.renpy_runtime.name}"
            elif result.engine_version:
                runtime_text = f"RUNTIME // AUTO REN'PY {result.engine_version}  //  OVERRIDE…"
            else:
                runtime_text = "RUNTIME // CHOOSE REN'PY ARM64…"
            self.runtime_button.configure(state="normal", text=runtime_text)
        else:
            self.runtime_button.configure(state="disabled", text="RUNTIME // AUTOMATIC")

        self.convert_btn.configure(state="normal" if result.buildable else "disabled")
        self.drop_label.configure(
            text="PAYLOAD LOCKED"
            if result.buildable
            else "DETECTED // MANUAL HANDLING REQUIRED"
        )
        self._set_status(
            f"Detected {result.engine_label}" if result.backend else "No supported engine detected",
            C_TEAL if result.backend else C_ERR,
        )
        for warning in result.warnings:
            self._log("Inspect: " + warning)

    def _inspection_failed(self, message: str) -> None:
        self.activity_progress.stop()
        self.activity_label.configure(text="CURRENT OPERATION // INSPECTION FAILED")
        self.inspection = None
        self.drop_label.configure(text="SCAN FAILED")
        self.engine_label.configure(text="Engine: inspection failed", text_color=C_ERR)
        self.convert_btn.configure(state="disabled")
        self._set_status("SCAN FAILED", C_ERR)
        self._log("Inspect error: " + message)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select game ZIP (Cancel to choose a folder)",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
        )
        if path:
            self._set_source(Path(path))
            return
        folder = filedialog.askdirectory(title="Select game folder")
        if folder:
            self._set_source(Path(folder))

    def _on_drop(self, event) -> None:
        try:
            paths = self.root.tk.splitlist(event.data)
            if paths:
                self._set_source(Path(paths[0]))
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _pick_output(self) -> None:
        folder = filedialog.askdirectory(title="Output folder", initialdir=str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self.out_label.configure(text=f"OUTPUT // {self.output_dir}")

    def _pick_renpy_runtime(self) -> None:
        folder = filedialog.askdirectory(
            title="Optional override: select matching Linux ARM64 Ren'Py runtime"
        )
        if folder:
            self.renpy_runtime = Path(folder)
            self.runtime_button.configure(
                text=f"Ren'Py override: {self.renpy_runtime.name}"
            )

    def _open_output(self) -> None:
        if self.last_archive and self.last_archive.exists():
            _open_path(self.last_archive.parent)
        elif self.last_output and self.last_output.exists():
            _open_path(self.last_output.parent)
        else:
            _open_path(self.output_dir)

    def _start_convert(self) -> None:
        if self._busy or self.source is None or self.inspection is None:
            return
        if (
            self.inspection.engine == "renpy"
            and self.renpy_runtime is None
            and not self.inspection.engine_version
        ):
            self._pick_renpy_runtime()
            if self.renpy_runtime is None:
                return

        source = self.source
        output = output_path_for_source(source, self.output_dir)
        force = bool(self.force_var.get())
        archive = bool(self.archive_var.get())

        self.log_box.delete("1.0", "end")
        self._log(f"Source: {source}")
        self._log(f"Engine: {self.inspection.engine_label}")
        self._log(f"Backend: {self.inspection.backend}")
        self._log(f"Output: {output}")
        self._set_busy(True)
        self._set_status("CONVERSION IN PROGRESS", C_TEAL)

        def worker() -> None:
            try:
                result = build_source(
                    source,
                    output=output,
                    renpy_runtime=self.renpy_runtime,
                    force=force,
                    archive=archive,
                    progress=self._progress_log,
                    stage_progress=self._set_progress,
                )
                self._dispatch(lambda: self._done(result))
            except ConversionError as exc:
                self._dispatch(lambda: self._fail(str(exc)))
            except Exception as exc:
                self._dispatch(lambda: self._fail(f"Unexpected error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, result: UnifiedBuildResult) -> None:
        self._set_progress(1.0, "Complete")
        self.last_output = result.output_path
        self.last_archive = result.archive_path
        self._set_busy(False)
        self._log(f"Built: {result.output_path}")
        if result.archive_path:
            self._log(f"Archive: {result.archive_path}")
        for warning in result.warnings:
            self._log("Warning: " + warning)
        target = result.archive_path or result.output_path
        self._set_status(f"Done → {target}", C_OK)
        messagebox.showinfo(
            APP_NAME,
            f"Converted {result.game_name or result.output_path.name}.\n\n"
            f"Build directory:\n{result.output_path}\n\n"
            + (f"Transfer archive:\n{result.archive_path}\n" if result.archive_path else ""),
        )

    def _fail(self, message: str) -> None:
        self._set_busy(False)
        self.activity_label.configure(text="CURRENT OPERATION // FAILED")
        self._log("ERROR: " + message)
        self._set_status("CONVERSION FAILED", C_ERR)
        messagebox.showerror(APP_NAME, message)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ConverterApp().run()


if __name__ == "__main__":
    main()
