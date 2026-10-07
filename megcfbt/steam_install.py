"""Install converted Linux ARM64 builds directly into Steam on Steam Frame."""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import shutil
import socket
import struct
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus

from megcfbt.frame_package import (
    FramePackageError,
    discover_artwork,
    load_frame_metadata,
)


class SteamInstallError(RuntimeError):
    """Raised when a converted build cannot be registered with local Steam."""


_DEVKIT_ROOT = Path.home() / "devkit-game"
_RESERVED_IDS = {"steam", "steamdeckard", "steamvr", "steamvrdeckard", "devkit-steam"}
_NEW_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,63}$")
_MAX_ARTWORK = 12 * 1024 * 1024
_ARTWORK_TYPES = {"grid": 0, "hero": 1, "logo": 2, "wide": 3}


def is_supported_host() -> bool:
    return platform.system() == "Linux" and platform.machine().lower() in {
        "aarch64",
        "arm64",
    }


def title_id(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(name or "").strip()).strip("_")
    value = value[:64].strip("_")
    if not value:
        raise SteamInstallError("Steam title needs a name with letters or digits")
    if value[0].isdigit():
        value = "_" + value[:63]
    if len(value) < 2 or value.lower() in _RESERVED_IDS:
        value += "_game"
    if not _NEW_ID_RE.fullmatch(value):
        raise SteamInstallError(f"Could not make a safe Steam title id from {name!r}")
    return value


def _steam_pid() -> int:
    path = Path.home() / ".steam" / "steam.pid"
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (OSError, ValueError) as exc:
        raise SteamInstallError("Steam must be running before adding the converted game") from exc
    return pid


def _send_devkit_command(command: str) -> None:
    pipe_path = Path.home() / ".steam" / "steam.pipe"
    token_path = Path.home() / ".steam" / "steam.token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
        with pipe_path.open("wb", buffering=0) as pipe:
            pipe.write(f"devkit-1 steam://devkit-1/{token}/{command}\n".encode("utf-8"))
    except OSError as exc:
        raise SteamInstallError(f"Could not talk to Steam's devkit pipe: {exc}") from exc


def _wait_for_response(path: Path, *, timeout: int = 12) -> str:
    error_path = Path(str(path) + ".error")
    lock_path = Path(str(path) + ".lock")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if error_path.exists():
            try:
                message = error_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                message = "Steam returned an unknown registration error"
            raise SteamInstallError(message or "Steam refused the devkit shortcut")
        if path.exists() and not lock_path.exists():
            return path.read_text(encoding="utf-8", errors="replace").strip()
        time.sleep(0.2)
    raise SteamInstallError("Steam did not confirm the Devkit Game registration")


def _register_devkit_game(gameid: str) -> str:
    _steam_pid()
    with tempfile.TemporaryDirectory(prefix="megcfbt-steam-") as temporary:
        response = Path(temporary) / "registered"
        command = (
            "create-shortcut?response="
            + quote_plus(str(response))
            + "&gameid="
            + quote_plus(gameid)
        )
        _send_devkit_command(command)
        return _wait_for_response(response)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _install_tree(source: Path, gameid: str, launcher: str) -> Path:
    _DEVKIT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = _DEVKIT_ROOT / gameid
    staging = _DEVKIT_ROOT / f".{gameid}.megcfbt-upload"
    backup = _DEVKIT_ROOT / f".{gameid}.megcfbt-old"

    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    try:
        shutil.copytree(
            source,
            staging,
            symlinks=False,
            ignore_dangling_symlinks=True,
        )
        launcher_path = staging / launcher
        if not launcher_path.is_file():
            raise SteamInstallError(f"Converted launcher is missing: {launcher}")
        launcher_path.chmod(launcher_path.stat().st_mode | 0o755)

        if destination.exists():
            destination.rename(backup)
        staging.rename(destination)
        shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and not destination.exists():
            backup.rename(destination)
        raise

    _write_json(_DEVKIT_ROOT / f"{gameid}-argv.json", [launcher])
    _write_json(_DEVKIT_ROOT / f"{gameid}-env.json", {})
    _write_json(
        _DEVKIT_ROOT / f"{gameid}-settings.json",
        {
            "steam_play": "0",
            "compat_tool": "SteamLinuxRuntime_4-arm64",
        },
    )
    return destination


class _WebSocket:
    def __init__(self, url: str, *, timeout: int = 20):
        if not url.startswith("ws://"):
            raise SteamInstallError("Steam returned an unsupported WebSocket URL")
        host_port, path = url[len("ws://") :].split("/", 1)
        host, port = host_port.rsplit(":", 1)
        self.socket = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        received = b""
        while b"\r\n\r\n" not in received:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise SteamInstallError("Steam closed the artwork connection")
            received += chunk
        header, self.rest = received.split(b"\r\n\r\n", 1)
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise SteamInstallError("Steam refused the artwork WebSocket")

    def _read(self, count: int) -> bytes:
        while len(self.rest) < count:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise EOFError
            self.rest += chunk
        output, self.rest = self.rest[:count], self.rest[count:]
        return output

    def send(self, payload: str) -> None:
        data = payload.encode("utf-8")
        mask = os.urandom(4)
        length = len(data)
        if length < 126:
            header = bytes([0x81, 0x80 | length])
        elif length < 65536:
            header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", length)
        else:
            header = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", length)
        encoded = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.socket.sendall(header + mask + encoded)

    def recv(self) -> str:
        message = b""
        while True:
            first, second = self._read(2)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            if second & 0x80:
                mask = self._read(4)
                body = self._read(length)
                body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
            else:
                body = self._read(length)
            message += body
            if first & 0x80:
                return message.decode("utf-8")


def _shared_context_url() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/json", timeout=5) as response:
            targets = json.load(response)
    except Exception as exc:
        raise SteamInstallError("Steam library UI debug endpoint is unavailable") from exc
    for target in targets:
        if target.get("title") == "SharedJSContext" and target.get("webSocketDebuggerUrl"):
            return str(target["webSocketDebuggerUrl"])
    raise SteamInstallError("Steam SharedJSContext is unavailable")


def _evaluate(javascript: str):
    ws = _WebSocket(_shared_context_url())
    ws.send(
        json.dumps(
            {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": javascript,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            }
        )
    )
    while True:
        response = json.loads(ws.recv())
        if response.get("id") != 1:
            continue
        result = response.get("result", {})
        if "exceptionDetails" in result:
            raise SteamInstallError("Steam library UI rejected shortcut configuration")
        return result.get("result", {}).get("value")


def _shortcut_appid(gameid: str, directory: Path) -> int | None:
    root = directory.as_posix()
    script = f"""(async () => {{
      const apps = appStore.allApps.filter(a => a.app_type === 1073741824);
      for (const app of apps) {{
        if (app.devkit_gameid === {json.dumps(gameid)}) return app.appid;
        let details = typeof appDetailsStore !== "undefined" && appDetailsStore.GetAppDetails(app.appid);
        if (!details && typeof SteamClient.Apps.RegisterForAppDetails === "function") {{
          details = await new Promise(resolve => {{
            let reg;
            const timer = setTimeout(() => {{ if (reg) reg.unregister(); resolve(null); }}, 2500);
            reg = SteamClient.Apps.RegisterForAppDetails(app.appid, value => {{
              clearTimeout(timer);
              setTimeout(() => reg && reg.unregister());
              resolve(value);
            }});
          }});
        }}
        if (!details) continue;
        const exe = String(details.strShortcutExe || "").replace(/^"|"$/g, "");
        const start = String(details.strShortcutStartDir || "").replace(/^"|"$/g, "");
        if (exe.startsWith({json.dumps(root + "/")}) || start === {json.dumps(root)}) return app.appid;
      }}
      return null;
    }})()"""
    value = _evaluate(script)
    return int(value) if value is not None else None


def _artwork_payload(build_directory: Path) -> tuple[dict[str, tuple[str, str]], str | None]:
    custom: dict[str, tuple[str, str]] = {}
    icon_path: str | None = None
    for slot, path in discover_artwork(build_directory).items():
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > _MAX_ARTWORK:
            continue
        extension = path.suffix.lower().lstrip(".")
        extension = "jpg" if extension == "jpeg" else extension
        if extension not in {"png", "jpg"}:
            continue
        if slot == "icon":
            icon_path = path.as_posix()
        elif slot in _ARTWORK_TYPES:
            custom[slot] = (extension, base64.b64encode(data).decode("ascii"))
    return custom, icon_path


def _configure_shortcut(
    appid: int,
    *,
    name: str,
    directory: Path,
    build_directory: Path,
) -> list[str]:
    custom, icon = _artwork_payload(build_directory)
    images = [
        [_ARTWORK_TYPES[slot], extension, encoded]
        for slot, (extension, encoded) in custom.items()
    ]
    script = f"""(async () => {{
      const id = {int(appid)};
      const warnings = [];
      SteamClient.Apps.SetShortcutName(id, {json.dumps(name)});
      if (typeof SteamClient.Apps.SetShortcutSortAs === "function")
        SteamClient.Apps.SetShortcutSortAs(id, {json.dumps(name)});
      if ({json.dumps(icon)} && typeof SteamClient.Apps.SetShortcutIcon === "function")
        SteamClient.Apps.SetShortcutIcon(id, {json.dumps(icon)});
      if ({json.dumps(bool(images))}) {{
        if (typeof SteamClient.Apps.SetCustomArtworkForApp !== "function") {{
          warnings.push("Steam custom artwork API unavailable");
        }} else {{
          for (const [type, ext, data] of {json.dumps(images)}) {{
            try {{
              if (typeof SteamClient.Apps.ClearCustomArtworkForApp === "function")
                await SteamClient.Apps.ClearCustomArtworkForApp(id, type);
              await SteamClient.Apps.SetCustomArtworkForApp(id, data, ext, type);
            }} catch (error) {{
              warnings.push("Steam artwork slot " + type + ": " + String(error));
            }}
          }}
        }}
      }}
      return warnings;
    }})()"""
    result = _evaluate(script)
    return [str(item) for item in result] if isinstance(result, list) else []


def install_build(
    build_directory: Path | str,
    *,
    progress=None,
) -> dict:
    """Copy a converted build into ~/devkit-game and register it with local Steam."""

    if not is_supported_host():
        raise SteamInstallError("Direct Steam install is only available on Linux ARM64")

    source = Path(build_directory).expanduser().resolve()
    if not source.is_dir():
        raise SteamInstallError(f"Converted build directory does not exist: {source}")

    try:
        metadata = load_frame_metadata(source)
    except FramePackageError as exc:
        raise SteamInstallError(str(exc)) from exc

    name = str(metadata.get("name") or source.name)
    launcher = str(metadata["launcher"])
    gameid = title_id(name)
    step = progress or (lambda _message: None)

    step("Preparing Steam Devkit Game")
    destination = _install_tree(source, gameid, launcher)
    step("Registering with Steam")
    registration = _register_devkit_game(gameid)

    warnings: list[str] = []
    try:
        appid = _shortcut_appid(gameid, destination)
        if appid is None:
            warnings.append("Steam registered the game, but its library shortcut was not found for artwork/name cleanup")
        else:
            warnings.extend(
                _configure_shortcut(
                    appid,
                    name=name,
                    directory=destination,
                    build_directory=destination,
                )
            )
    except SteamInstallError as exc:
        appid = None
        warnings.append(str(exc))

    step("Added to Steam")
    return {
        "id": gameid,
        "name": name,
        "directory": str(destination),
        "launcher": launcher,
        "runtime": "SteamLinuxRuntime_4-arm64",
        "registration": registration,
        "appid": appid,
        "warnings": warnings,
    }
