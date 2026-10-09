"""Consent-gated owned Steam entry integration; never changes ownership or AppIDs."""
import base64, hashlib, json, os, socket, struct, urllib.request
from pathlib import Path

class _WebSocket:
    def __init__(self, url: str, *, timeout: int = 20):
        if not url.startswith("ws://"):
            raise RuntimeError("Steam returned an unsupported WebSocket URL")
        host_port, path = url[len("ws://") :].split("/", 1)
        host, port = host_port.rsplit(":", 1)
        if host not in {"127.0.0.1", "localhost"} or int(port) != 8080:
            raise RuntimeError("Steam debugger must be local")
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
                raise RuntimeError("Steam closed the artwork connection")
            received += chunk
        header, self.rest = received.split(b"\r\n\r\n", 1)
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        headers = dict(line.split(b":", 1) for line in header.split(b"\r\n")[1:] if b":" in line)
        accept = next((v.strip() for k,v in headers.items() if k.lower() == b"sec-websocket-accept"), b"")
        if accept != expected or b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise RuntimeError("Steam refused the artwork WebSocket")

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
            if length > 4*1024*1024:
                raise RuntimeError("Steam debugger response exceeds limit")
            if first & 0x0f == 8:
                raise RuntimeError("Steam debugger connection closed")
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
        raise RuntimeError("Steam library UI debug endpoint is unavailable") from exc
    for target in targets:
        if target.get("title") == "SharedJSContext" and target.get("webSocketDebuggerUrl"):
            return str(target["webSocketDebuggerUrl"])
    raise RuntimeError("Steam SharedJSContext is unavailable")


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
        ws.socket.close()
        if "exceptionDetails" in result:
            raise RuntimeError("Steam library UI rejected shortcut configuration")
        return result.get("result", {}).get("value")



APP_ID = 2868840  # Publisher's real owned Steam entry; never synthesized.


def inspect():
    state = _evaluate("""(() => {
      const app = appStore.allApps.find(a => a.appid === 2868840);
      const details = appDetailsStore.GetAppDetails(2868840);
      return {present: !!app, installed: !!(app && app.installed),
        setter: typeof SteamClient.Apps.SetAppLaunchOptions === 'function',
        launch_options: details ? details.strLaunchOptions : null};
    })()""")
    if not isinstance(state, dict) or not state.get('present') or not state.get('installed'):
        raise RuntimeError('Open Steam with the owned, installed Slay the Spire 2 entry available.')
    if not state.get('setter') or not isinstance(state.get('launch_options'), str):
        raise RuntimeError('This Steam client does not expose supported launch configuration. No settings changed.')
    return state


def set_options(expected, replacement):
    # Compare in the Steam UI context immediately before mutation. Never overwrite an intervening user edit.
    script = """(() => {
      const d = appDetailsStore.GetAppDetails(2868840);
      if (!d || d.strLaunchOptions !== %s) throw new Error('Steam launch settings changed; inspect again');
      SteamClient.Apps.SetAppLaunchOptions(2868840, %s);
      return true;
    })()""" % (json.dumps(expected), json.dumps(replacement))
    if _evaluate(script) is not True:
        raise RuntimeError('Steam did not acknowledge launch configuration')
    import time
    for _ in range(20):
        if inspect()['launch_options'] == replacement:
            return
        time.sleep(.1)
    raise RuntimeError('Steam launch configuration was not confirmed. Backup retained for recovery.')


def configure(root, *, isolated=False, consent=False):
    if not consent:
        raise RuntimeError('Explicit consent is required to configure the owned Steam entry')
    from verify_output import verify
    root = Path(root).resolve()
    report = verify(root, check_modes=True)
    if report['errors']:
        raise RuntimeError('Generated output failed verification; Steam settings were not changed')
    state = inspect()
    command = '"' + str(root/'play-steam.sh') + '"' + (' --isolated-user-data' if isolated else '') + ' %command%'
    directory = root.parent/'steam-integration'
    directory.mkdir(mode=0o700, exist_ok=True)
    backup = directory/'launch-backup.json'
    if backup.exists():
        record = json.loads(backup.read_bytes())
        if record['installed'] != command:
            raise RuntimeError('A different launch configuration already has a backup here; restore it first')
        if state['launch_options'] == command:
            return {'configured': True, 'backup': str(backup)}
        if state['launch_options'] != record['previous']:
            raise RuntimeError('Steam settings changed since this backup; no settings changed')
    else:
        record = {'kind': 'megcfbt-owned-steam-launch-v1', 'appid': APP_ID,
                  'previous': state['launch_options'], 'installed': command}
        with backup.open('x') as stream:
            os.chmod(backup, 0o600)
            json.dump(record, stream)
            stream.flush(); os.fsync(stream.fileno())
    set_options(state['launch_options'], command)
    return {'configured': True, 'backup': str(backup)}


def restore(root, *, consent=False):
    if not consent:
        raise RuntimeError('Explicit consent is required to restore Steam launch settings')
    backup = Path(root).resolve().parent/'steam-integration/launch-backup.json'
    record = json.loads(backup.read_bytes())
    if record.get('kind') != 'megcfbt-owned-steam-launch-v1' or record.get('appid') != APP_ID:
        raise RuntimeError('Unrecognized Steam backup')
    current = inspect()['launch_options']
    if current == record['previous']:
        return {'restored': True}
    if current != record['installed']:
        raise RuntimeError('Steam settings were edited after conversion; Restore will not overwrite them')
    set_options(current, record['previous'])
    return {'restored': True}

if __name__ == '__main__':
    print(json.dumps(inspect()))
