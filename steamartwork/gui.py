"""Frame-local artwork editor, usable independently of the game converter."""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tempfile

from steamartwork import APP_NAME
from steamartwork import backend


class ArtworkApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        self.entries = []
        self.visible = []
        self.selected = None
        self.profile = None
        self.pending = {}
        self.previews = {}
        self.last_backup = None
        self.busy = False
        self.downloads = tempfile.TemporaryDirectory(prefix="steam-artwork-")
        self.results = queue.Queue()
        root.title(APP_NAME)
        root.geometry("1120x850")
        root.minsize(980, 640)
        root.configure(bg="#101722")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background="#101722", foreground="#edf2f7", font=("sans", 11))
        style.configure("TButton", padding=9, background="#29485a")
        style.map("TButton", background=[("active", "#376478")])
        style.configure("TEntry", fieldbackground="#1c2939", foreground="#edf2f7")
        style.configure("TCombobox", fieldbackground="#1c2939", foreground="#edf2f7")
        style.map("TCombobox", fieldbackground=[("readonly", "#1c2939")],
                  foreground=[("readonly", "#edf2f7")])
        style.configure("Title.TLabel", font=("sans", 24, "bold"))
        style.configure("Muted.TLabel", foreground="#a6b8c9")
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Choose a non-Steam entry. Pick your artwork. Apply.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="Steam profile").pack(side="left", padx=(0, 8))
        self.profile_var = tk.StringVar()
        self.profiles = backend.discover_profiles()
        self.profile_box = ttk.Combobox(top, textvariable=self.profile_var, state="readonly",
                                       values=[str(p) for p in self.profiles])
        self.profile_box.pack(side="left", fill="x", expand=True)
        self.profile_box.bind("<<ComboboxSelected>>", self.change_profile)
        ttk.Button(top, text="Browse…", command=self.browse_profile).pack(side="left", padx=8)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left")
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=16)
        left = ttk.Frame(body, width=280)
        left.pack(side="left", fill="y", padx=(0, 20))
        ttk.Label(left, text="1. Choose entry", font=("sans", 14, "bold")).pack(anchor="w")
        self.search = tk.StringVar()
        ttk.Entry(left, textvariable=self.search).pack(fill="x", pady=8)
        self.search.trace_add("write", lambda *_: self.filter_entries())
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, bg="#1c2939", fg="#edf2f7",
                                 selectbackground="#376478", exportselection=False,
                                 font=("sans", 11), width=28, borderwidth=0, highlightthickness=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.bind("<<ListboxSelect>>", self.pick_entry)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="2. Choose images", font=("sans", 14, "bold")).pack(anchor="w")
        self.entry_label = ttk.Label(right, text="Select an entry to begin.", wraplength=580)
        self.entry_label.pack(anchor="w", pady=(8, 4))
        self.detail_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=580)
        self.detail_label.pack(anchor="w", pady=(0, 8))
        online = ttk.Frame(right)
        online.pack(fill="x", pady=(0, 8))
        ttk.Label(online, text="SteamGridDB (optional)", font=("sans", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.api_key = tk.StringVar()
        self.game_id = tk.StringVar()
        ttk.Label(online, text="API key").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(online, textvariable=self.api_key, show="•").grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Label(online, text="Game ID").grid(row=2, column=0, sticky="w")
        ttk.Entry(online, textvariable=self.game_id, width=14).grid(row=2, column=1, sticky="ew", padx=8)
        self.fetch_button = ttk.Button(online, text="Fetch artwork", command=self.fetch)
        self.fetch_button.grid(row=2, column=2, sticky="e")
        online.columnconfigure(1, weight=1)
        ttk.Label(online, text="Use the ID from steamgriddb.com/game/ID. Key stays in memory.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        scrolling = ttk.Frame(right)
        scrolling.pack(fill="both", expand=True)
        canvas = tk.Canvas(scrolling, bg="#101722", highlightthickness=0, width=560)
        self.artwork_canvas = canvas
        bar = ttk.Scrollbar(scrolling, orient="vertical", command=canvas.yview)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=bar.set)
        rows = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self.image_labels, self.path_vars = {}, {}
        for slot, (label, _, recommendation) in backend.SLOTS.items():
            row = ttk.Frame(rows)
            row.pack(fill="x", pady=6)
            preview_frame = ttk.Frame(row, width=140, height=88)
            preview_frame.pack(side="left", padx=(0, 12))
            preview_frame.pack_propagate(False)
            preview = tk.Label(preview_frame, bg="#1c2939", fg="#a6b8c9", text="No artwork",
                               width=18, height=5)
            preview.pack(fill="both", expand=True)
            self.image_labels[slot] = preview
            info = ttk.Frame(row)
            info.pack(side="left", fill="x", expand=True)
            ttk.Label(info, text=label, font=("sans", 12, "bold")).pack(anchor="w")
            ttk.Label(info, text=f"Suggested: {recommendation}", style="Muted.TLabel").pack(anchor="w")
            self.path_vars[slot] = tk.StringVar(value="Keep current artwork")
            ttk.Label(info, textvariable=self.path_vars[slot], wraplength=340,
                      style="Muted.TLabel").pack(anchor="w", pady=4)
            buttons = ttk.Frame(info)
            buttons.pack(anchor="w")
            ttk.Button(buttons, text="Browse…", command=lambda s=slot: self.browse_image(s)).pack(side="left")
            ttk.Button(buttons, text="Keep current", command=lambda s=slot: self.keep_current(s)).pack(side="left", padx=6)
        def bind_scroll(widget):
            widget.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, "units"), add="+")
            widget.bind("<Button-4>", lambda _: canvas.yview_scroll(-1, "units"), add="+")
            widget.bind("<Button-5>", lambda _: canvas.yview_scroll(1, "units"), add="+")
            for child in widget.winfo_children():
                bind_scroll(child)
        bind_scroll(canvas)
        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        self.apply_button = ttk.Button(footer, text="3. Apply artwork", command=self.apply, state="disabled")
        self.apply_button.pack(side="right")
        self.undo_button = ttk.Button(footer, text="Undo last apply", command=self.undo, state="disabled")
        self.undo_button.pack(side="right", padx=8)
        self.status = tk.StringVar(value="PNG and JPEG supported. Unselected artwork stays as it is.")
        ttk.Label(outer, textvariable=self.status, wraplength=1000).pack(anchor="w", pady=(12, 4))
        ttk.Label(outer, text="Exit Steam before applying, then reopen it to reload artwork. "
                  "Replaced images are backed up automatically.", style="Muted.TLabel", wraplength=1000).pack(anchor="w")
        if self.profiles:
            self.profile_var.set(str(self.profiles[0]))
            self.change_profile()
        else:
            self.status.set("No saved Steam shortcuts found. Browse to your Steam userdata/<account> folder.")
        root.after(100, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        if not self.busy:
            self.api_key.set("")
            self.downloads.cleanup()
            self.root.destroy()

    def error(self, exc):
        from tkinter import messagebox
        messagebox.showerror(APP_NAME, str(exc), parent=self.root)

    def browse_profile(self):
        from tkinter import filedialog
        if self.busy:
            return
        path = filedialog.askdirectory(title="Choose Steam userdata/<account> folder", parent=self.root)
        if path:
            self.profile_var.set(path)
            self.change_profile()

    def change_profile(self, _event=None):
        if self.busy:
            self.profile_var.set(str(self.profile))
            return
        self.profile = Path(self.profile_var.get()).expanduser()
        self.last_backup = None
        self.undo_button.configure(state="disabled")
        self.refresh()

    def refresh(self):
        if self.busy or self.profile is None:
            return
        self.selected = None
        self.pending.clear()
        self.game_id.set("")
        self.apply_button.configure(state="disabled")
        try:
            self.entries = backend.shortcuts(self.profile)
            self.status.set(f"Found {len(self.entries)} non-Steam entries. Search by name or AppID.")
        except (OSError, ValueError) as exc:
            self.entries = []
            self.error(exc)
        self.filter_entries()
        self.show_images()

    def filter_entries(self):
        if self.busy:
            return
        term = self.search.get().casefold()
        self.visible = [e for e in self.entries if term in f"{e.name} {e.appid}".casefold()]
        self.listbox.delete(0, "end")
        for entry in self.visible:
            self.listbox.insert("end", f"{entry.name}  [{entry.appid}]")
        if self.selected in self.visible:
            self.listbox.selection_set(self.visible.index(self.selected))

    def pick_entry(self, _event=None):
        if self.busy or not self.listbox.curselection():
            return
        entry = self.visible[self.listbox.curselection()[0]]
        if entry != self.selected:
            self.selected = entry
            self.pending.clear()
            self.game_id.set("")
            self.show_images()

    def show_images(self):
        from PIL import Image, ImageTk, ImageOps
        self.entry_label.configure(text=self.selected.name if self.selected else "Select an entry to begin.")
        self.detail_label.configure(text=f"AppID {self.selected.appid} · {self.selected.executable}" if self.selected else "")
        for slot, label in self.image_labels.items():
            path = self.pending.get(slot)
            chosen = path is not None
            if path is None and self.selected:
                path = next((p for p in backend.artwork_paths(self.profile, self.selected, slot) if p.is_file()), None)
            self.path_vars[slot].set(f"Selected: {path.name}" if chosen else "Keep current artwork")
            self.previews.pop(slot, None)
            label.configure(image="", text="No artwork", width=18, height=5)
            if path:
                try:
                    with Image.open(path) as source:
                        if source.width * source.height > 40_000_000:
                            raise ValueError("Image too large")
                        preview = ImageOps.exif_transpose(source).convert("RGBA")
                        preview.thumbnail((140, 88))
                    self.previews[slot] = ImageTk.PhotoImage(preview)
                    label.configure(image=self.previews[slot], text="", width=140, height=88)
                except (OSError, ValueError, Image.DecompressionBombError):
                    label.configure(text="Preview unavailable")
        self.apply_button.configure(state="normal" if self.selected and self.pending and not self.busy else "disabled")

    def browse_image(self, slot):
        from tkinter import filedialog
        if self.busy or self.selected is None:
            return
        path = filedialog.askopenfilename(title=f"Choose {backend.SLOTS[slot][0]}", parent=self.root,
                                         filetypes=[("PNG and JPEG images", "*.png *.jpg *.jpeg"), ("All files", "*")])
        if path:
            try:
                backend.read_image(Path(path))
            except (OSError, ValueError) as exc:
                self.error(exc)
                return
            self.pending[slot] = Path(path)
            self.show_images()

    def keep_current(self, slot):
        if not self.busy:
            self.pending.pop(slot, None)
            self.show_images()

    def start_work(self, operation, function):
        self.busy = True
        self.apply_button.configure(state="disabled")
        self.undo_button.configure(state="disabled")
        self.fetch_button.configure(state="disabled")
        self.status.set({"apply": "Applying artwork…", "undo": "Restoring artwork…",
                         "fetch": "Fetching SteamGridDB images for review…"}[operation])
        def work():
            try:
                self.results.put((operation, function(), None))
            except Exception as exc:
                self.results.put((operation, None, exc))
        threading.Thread(target=work, daemon=True).start()

    def fetch(self):
        from steamartwork.steamgriddb import fetch_artwork
        if self.busy or self.selected is None:
            return
        slots = [slot for slot in backend.SLOTS if slot not in self.pending]
        if not slots:
            self.status.set("All four images are selected. Use Keep current on a slot to fetch a replacement.")
            return
        key, game_id = self.api_key.get(), self.game_id.get().strip()
        if not key.strip() or not game_id:
            self.error("Enter your SteamGridDB API key and the game's SteamGridDB ID first.")
            return
        directory = Path(tempfile.mkdtemp(dir=self.downloads.name))
        self.start_work("fetch", lambda: fetch_artwork(key, game_id, directory, slots=slots))

    def apply(self):
        if not self.busy and self.selected and self.pending:
            profile, entry, selections = self.profile, self.selected, dict(self.pending)
            self.start_work("apply", lambda: backend.apply_artwork(profile, entry, selections))

    def undo(self):
        if not self.busy and self.last_backup:
            profile, backup = self.profile, self.last_backup
            self.start_work("undo", lambda: backend.undo_artwork(profile, backup))

    def poll(self):
        try:
            operation, result, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if error:
                self.status.set("SteamGridDB lookup failed. Local browsing is still available." if operation == "fetch"
                                else "Artwork operation failed. See the error for recovery details.")
                self.error(error)
            elif operation == "fetch":
                title, images, warnings = result
                self.pending.update(images)
                message = f"Fetched {len(images)} images for {title}. Review, then Apply."
                self.status.set(message + (" " + "; ".join(warnings) if warnings else ""))
            else:
                self.pending.clear()
                self.last_backup = result if operation == "apply" else None
                self.status.set(f"Applied. Reopen Steam to see changes. Backup: {result}" if operation == "apply"
                                else "Previous artwork restored. Reopen Steam to see changes.")
            self.undo_button.configure(state="normal" if self.last_backup else "disabled")
            self.fetch_button.configure(state="normal")
            self.show_images()
            self.filter_entries()
        self.root.after(100, self.poll)


def main(argv=None):
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--verify-gui-startup", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    if args.verify_gui_startup and args.receipt is None:
        parser.error("--verify-gui-startup requires --receipt")
    try:
        import tkinter as tk
        from PIL import Image, ImageTk  # noqa: F401
    except ImportError as exc:
        raise SystemExit('Install tkinter and this companion with: pip install -e ".[artwork-gui]"') from exc
    root = tk.Tk()
    app = ArtworkApp(root)
    if args.verify_gui_startup:
        try:
            root.withdraw()
            root.update_idletasks()
            metadata = Path(__file__).with_name("_build_info.json")
            identity = json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else None
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps({"state": "complete", "app_name": APP_NAME,
                "frozen": bool(getattr(sys, "frozen", False)), "build_info": identity}, indent=2) + "\n", encoding="utf-8")
        finally:
            app.downloads.cleanup()
            root.destroy()
    else:
        root.mainloop()
    return 0
