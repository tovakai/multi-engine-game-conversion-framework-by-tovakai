"""Small real-window input probe; no game assets and no controller hooks."""
import json
import os
from pathlib import Path
import time
import tkinter as tk

root = tk.Tk()
root.title("MEGCFBT Controller Input Test")
root.geometry("1100x720")
root.configure(bg="#101722")
tk.Label(root, text="Controller input test", bg="#101722", fg="#49d3c6",
         font=("sans", 24, "bold")).pack(pady=12)
tk.Label(root, text="D-pad / left stick: move square    •    R3: toggle pointer    •    RT: click/drag    •    LT: right-click\n"
         "Press R3 again: right stick stops moving the pointer. Escape closes this test.",
         bg="#101722", fg="white", font=("sans", 13)).pack(pady=8)
status = tk.StringVar(value="Try both movement controls, then press R3 and move the right stick.")
tk.Label(root, textvariable=status, bg="#101722", fg="#ff8452", font=("sans", 14)).pack(pady=8)
canvas = tk.Canvas(root, width=1040, height=500, bg="#1c2939", highlightthickness=0)
canvas.pack(fill="both", expand=True, padx=20, pady=20)
player = canvas.create_rectangle(100, 100, 150, 150, fill="#49d3c6", outline="")
target = canvas.create_rectangle(500, 160, 760, 320, fill="#29485a", outline="#edf2f7", width=2)
canvas.create_text(630, 240, text="Click inside\nHold RT and drag", fill="white", font=("sans", 18))
log = Path("/tmp/megcfbt-controller-input-events.jsonl").open("a", buffering=1)
def record(kind, **values):
    log.write(json.dumps({"time": time.time(), "kind": kind, **values}) + "\n")
record("start", environment={k: os.environ.get(k) for k in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "SteamAppId", "SteamGameId")})
def key(event):
    record("key", key=event.keysym)
    movement = {"Up": (0, -10), "Down": (0, 10), "Left": (-10, 0), "Right": (10, 0)}
    if event.keysym in movement:
        canvas.move(player, *movement[event.keysym])
        status.set("Movement received: " + event.keysym)
    elif event.keysym == "Escape":
        root.destroy()
def pointer(event, kind):
    record(kind, x=event.x, y=event.y, button=getattr(event, "num", None))
    status.set(f"{kind}: ({event.x}, {event.y})")
root.bind("<KeyPress>", key)
root.bind("<KeyRelease>", lambda e: record("key-release", key=e.keysym))
canvas.bind("<Motion>", lambda e: pointer(e, "motion"))
canvas.bind("<ButtonPress>", lambda e: pointer(e, "press"))
canvas.bind("<ButtonRelease>", lambda e: pointer(e, "release"))
canvas.bind("<B1-Motion>", lambda e: pointer(e, "drag"))
root.bind("<FocusOut>", lambda _: record("focus-out"))
root.bind("<FocusIn>", lambda _: record("focus-in"))
root.after(1500, root.focus_force)
try:
    root.mainloop()
finally:
    record("exit")
    log.close()
