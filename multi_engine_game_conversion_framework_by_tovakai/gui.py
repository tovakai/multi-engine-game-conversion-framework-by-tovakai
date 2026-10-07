"""Desktop frontend for Multi-Engine Game Conversion Framework by Tovakai."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from rpgmframe.runtime import DEFAULT_NWJS_VERSION

from .builder import BuildError, build_game
from .detector import inspect_source

APP_NAME = "Multi-Engine Game Conversion Framework by Tovakai"
APP_TAG = "Runtime conversion tooling for Linux ARM64"

C_BG = "#07111f"
C_PANEL = "#12233a"
C_PANEL_2 = "#1a3050"
C_BORDER = "#2a4a6a"
C_TEXT = "#f0e6d8"
C_MUTED = "#9eb0c4"
C_ACCENT = "#ff7a45"
C_ACCENT_HOVER = "#ff9466"
C_TEAL = "#3db8a8"
C_OK = "#5ecf8e"
C_ERR = "#ff6b7a"

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
    except ImportError as exc:
        raise SystemExit("Tk is required for the desktop application.") from exc

    try:
        import customtkinter as _ctk
    except ImportError as exc:
        raise SystemExit(
            'Missing GUI dependency. Install with: pip install -e ".[gui]"'
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
    root.geometry("1120x820")
    root.minsize(940, 700)
    root.configure(fg_color=C_BG)
    return root


def _open_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


class ConverterApp:
    def __init__(self) -> None:
        self.root = _make_root()
        self.source: Path | None = None
        self.inspection = None
        self.last_output: Path | None = None
        self.output_dir = Path.home() / "Desktop"
        if not self.output_dir.is_dir():
            self.output_dir = Path.home()

        self._busy = False
        self._generation = 0
        self._queue: queue.Queue[Any] = queue.Queue()

        self.archive_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.nwjs_var = tk.StringVar(value=DEFAULT_NWJS_VERSION)
        self.renpy_version_var = tk.StringVar(value="")

        self._build_ui()
        self.root.after(30, self._drain_queue)

    def _build_ui(self) -> None:
        ctk.CTkFrame(self.root, fg_color=C_ACCENT, height=4, corner_radius=0).pack(fill="x")

        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(18, 8))
        ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=APP_TAG + "  ·  Ren'Py  ·  RPG Maker  ·  Godot",
            font=ctk.CTkFont(size=14),
            text_color=C_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        self.drop = ctk.CTkFrame(
            self.root,
            fg_color=C_PANEL,
            border_width=2,
            border_color=C_BORDER,
            corner_radius=16,
            height=120,
        )
        self.drop.pack(fill="x", padx=28, pady=(4, 12))
        self.drop.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop,
            text="Drop a game folder or archive here",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C_TEXT,
        )
        self.drop_label.pack(expand=True, pady=(22, 0))
        self.path_label = ctk.CTkLabel(
            self.drop,
            text="Ren'Py, RPG Maker XP/VX/VX Ace/MV/MZ, or Godot",
            font=ctk.CTkFont(size=13),
            text_color=C_MUTED,
        )
        self.path_label.pack(pady=(0, 18))

        if _HAS_DND:
            try:
                self.drop.drop_target_register(DND_FILES)
                self.drop.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        controls = ctk.CTkFrame(self.root, fg_color="transparent")
        controls.pack(fill="x", padx=28)
        ctk.CTkButton(
            controls, text="Browse…", width=120, height=40,
            fg_color=C_PANEL_2, hover_color=C_BORDER,
            command=self._browse,
        ).pack(side="left")
        self.convert_btn = ctk.CTkButton(
            controls, text="Convert", width=160, height=40,
            state="disabled", fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            text_color="#1a0f0a", font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_convert,
        )
        self.convert_btn.pack(side="left", padx=10)
        ctk.CTkButton(
            controls, text="Output folder…", width=130, height=40,
            fg_color="transparent", border_width=1, border_color=C_BORDER,
            command=self._pick_output,
        ).pack(side="right")
        ctk.CTkButton(
            controls, text="Open output", width=120, height=40,
            fg_color="transparent", border_width=1, border_color=C_BORDER,
            command=self._open_output,
        ).pack(side="right", padx=8)

        options = ctk.CTkFrame(self.root, fg_color="transparent")
        options.pack(fill="x", padx=28, pady=(8, 4))
        ctk.CTkCheckBox(
            options, text="Create transfer archive", variable=self.archive_var,
            fg_color=C_TEAL, hover_color=C_TEAL, border_color=C_BORDER,
        ).pack(side="left")
        ctk.CTkCheckBox(
            options, text="Replace existing output", variable=self.force_var,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, border_color=C_BORDER,
        ).pack(side="left", padx=18)

        ctk.CTkLabel(options, text="Ren'Py override", text_color=C_MUTED).pack(side="right", padx=(10, 4))
        ctk.CTkEntry(
            options, width=90, textvariable=self.renpy_version_var,
            placeholder_text="auto", fg_color=C_PANEL, border_color=C_BORDER,
        ).pack(side="right")
        ctk.CTkLabel(options, text="NW.js", text_color=C_MUTED).pack(side="right", padx=(10, 4))
        ctk.CTkEntry(
            options, width=90, textvariable=self.nwjs_var,
            fg_color=C_PANEL, border_color=C_BORDER,
        ).pack(side="right")

        self.output_label = ctk.CTkLabel(
            self.root, text=f"Output: {self.output_dir}",
            font=ctk.CTkFont(size=12), text_color=C_MUTED,
        )
        self.output_label.pack(anchor="e", padx=28)

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=10)

        left = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(
            left, text="Progress / backend log",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEAL,
        ).pack(anchor="w", padx=16, pady=(14, 4))
        self.log = ctk.CTkTextbox(
            left, fg_color=C_BG, text_color=C_TEXT, wrap="word", corner_radius=10,
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        right = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14, width=360)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        ctk.CTkLabel(
            right, text="Inspection",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEAL,
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self.info_labels = {}
        for key in ("Engine", "Version", "Backend", "Compatibility", "Game"):
            row = ctk.CTkFrame(right, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row, text=key, width=100, anchor="w", text_color=C_MUTED).pack(side="left")
            value = ctk.CTkLabel(row, text="—", anchor="w", justify="left", wraplength=210, text_color=C_TEXT)
            value.pack(side="left", fill="x", expand=True)
            self.info_labels[key] = value

        ctk.CTkLabel(
            right, text="Evidence / warnings",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C_MUTED,
        ).pack(anchor="w", padx=16, pady=(14, 4))
        self.inspection_text = ctk.CTkTextbox(
            right, height=210, fg_color=C_BG, text_color=C_MUTED, wrap="word",
        )
        self.inspection_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        footer = ctk.CTkFrame(self.root, fg_color=C_PANEL, corner_radius=10)
        footer.pack(fill="x", padx=28, pady=(0, 20))
        self.progress = ctk.CTkProgressBar(footer, progress_color=C_TEAL)
        self.progress.pack(fill="x", padx=14, pady=(12, 4))
        self.progress.set(0)
        self.status = ctk.CTkLabel(footer, text="Ready", text_color=C_MUTED, anchor="w")
        self.status.pack(fill="x", padx=14, pady=(0, 10))

    def _enqueue(self, fn, *args) -> None:
        self._queue.put((fn, args))

    def _drain_queue(self) -> None:
        try:
            while True:
                fn, args = self._queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(30, self._drain_queue)

    def _append(self, message: str) -> None:
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")

    def _on_drop(self, event) -> None:
        try:
            items = self.root.tk.splitlist(event.data)
            if items:
                self._set_source(Path(items[0]))
        except Exception:
            pass

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose game archive",
            filetypes=[
                ("Supported archives", "*.zip *.tar *.tar.gz *.tgz *.tar.bz2 *.tar.xz"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            path = filedialog.askdirectory(title="Choose game folder")
        if path:
            self._set_source(Path(path))

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output directory", initialdir=str(self.output_dir))
        if path:
            self.output_dir = Path(path)
            self.output_label.configure(text=f"Output: {self.output_dir}")

    def _open_output(self) -> None:
        target = self.last_output or self.output_dir
        _open_path(target if target.is_dir() else target.parent)

    def _set_source(self, path: Path) -> None:
        path = path.expanduser().resolve()
        self.source = path
        self.inspection = None
        self._generation += 1
        generation = self._generation
        self.drop_label.configure(text=path.name)
        self.path_label.configure(text=str(path))
        self.convert_btn.configure(state="disabled")
        self.status.configure(text="Inspecting…", text_color=C_MUTED)
        self._append(f"Inspecting {path}")
        threading.Thread(target=self._inspect_worker, args=(path, generation), daemon=True).start()

    def _inspect_worker(self, path: Path, generation: int) -> None:
        try:
            info = inspect_source(path)
            self._enqueue(self._apply_inspection, info, generation)
        except Exception as exc:
            self._enqueue(self._inspection_failed, str(exc), generation)

    def _apply_inspection(self, info, generation: int) -> None:
        if generation != self._generation:
            return
        self.inspection = info
        values = {
            "Engine": info.engine,
            "Version": info.engine_version or "unknown",
            "Backend": info.backend.value,
            "Compatibility": info.compatibility,
            "Game": info.game_name or "unknown",
        }
        for key, value in values.items():
            self.info_labels[key].configure(text=value)

        lines = []
        if info.evidence:
            lines.append("Evidence:")
            lines.extend(f"• {x}" for x in info.evidence)
        if info.warnings:
            if lines:
                lines.append("")
            lines.append("Warnings:")
            lines.extend(f"• {x}" for x in info.warnings)
        if not lines:
            lines.append("No warnings.")
        self.inspection_text.delete("1.0", "end")
        self.inspection_text.insert("1.0", "\n".join(lines))

        self.convert_btn.configure(state="normal" if info.buildable else "disabled")
        if info.buildable:
            self.status.configure(text=f"Ready: {info.engine}", text_color=C_OK)
            self._append(f"Detected {info.engine} via {info.backend.value}")
        else:
            self.status.configure(text="Recognized, but not buildable" if info.recognized else "Unsupported source", text_color=C_ERR)

    def _inspection_failed(self, message: str, generation: int) -> None:
        if generation != self._generation:
            return
        self.status.configure(text="Inspection failed", text_color=C_ERR)
        self._append("ERROR: " + message)

    def _set_progress(self, stage: str, fraction: float | None, detail: str | None) -> None:
        if fraction is not None:
            self.progress.set(max(0.0, min(1.0, fraction)))
        text = stage + (f" · {detail}" if detail else "")
        self.status.configure(text=text, text_color=C_MUTED)

    def _start_convert(self) -> None:
        if self._busy or self.source is None or self.inspection is None:
            return
        self._busy = True
        self.convert_btn.configure(state="disabled", text="Converting…")
        self.progress.set(0)
        self._append("")
        self._append(f"Converting with {self.inspection.backend.value} backend")
        threading.Thread(target=self._convert_worker, daemon=True).start()

    def _convert_worker(self) -> None:
        assert self.source is not None
        try:
            result = build_game(
                self.source,
                output_dir=self.output_dir,
                force=bool(self.force_var.get()),
                archive=bool(self.archive_var.get()),
                nwjs_runtime_version=self.nwjs_var.get().strip() or DEFAULT_NWJS_VERSION,
                renpy_version_override=self.renpy_version_var.get().strip() or None,
                progress=lambda stage, fraction, detail: self._enqueue(
                    self._set_progress, stage, fraction, detail
                ),
                log=lambda message: self._enqueue(self._append, message),
            )
            self._enqueue(self._conversion_done, result)
        except BuildError as exc:
            self._enqueue(self._conversion_failed, str(exc))
        except Exception as exc:
            self._enqueue(self._conversion_failed, f"Unexpected error: {exc}")

    def _conversion_done(self, result) -> None:
        self._busy = False
        self.last_output = result.output_path
        self.convert_btn.configure(state="normal", text="Convert")
        self.progress.set(1)
        self.status.configure(text=f"Done · {result.output_path.name}", text_color=C_OK)
        self._append(f"Done: {result.output_path}")
        for warning in result.warnings:
            self._append("warning: " + warning)
        messagebox.showinfo(APP_NAME, f"Conversion complete.\n\n{result.output_path}")

    def _conversion_failed(self, message: str) -> None:
        self._busy = False
        self.convert_btn.configure(state="normal", text="Convert")
        self.status.configure(text="Conversion failed", text_color=C_ERR)
        self._append("ERROR: " + message)
        messagebox.showerror(APP_NAME, message)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ConverterApp().run()


if __name__ == "__main__":
    main()
