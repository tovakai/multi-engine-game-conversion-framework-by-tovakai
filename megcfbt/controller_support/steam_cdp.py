"""Local Steam UI transport shared by FrameBench and controller setup."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request


class SteamClientError(RuntimeError):
    pass


class _WebSocket:
    def __init__(self, url: str, *, timeout: int = 20):
        if not url.startswith("ws://"):
            raise SteamClientError("Steam returned an unsupported WebSocket URL")
        host_port, path = url[len("ws://"):].split("/", 1)
        host, port = host_port.rsplit(":", 1)
        if host not in {"127.0.0.1", "localhost"} or int(port) != 8080:
            raise SteamClientError("Steam debugger must be local")
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
                raise SteamClientError("Steam closed the debugger connection")
            received += chunk
        header, self.rest = received.split(b"\r\n\r\n", 1)
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        headers = dict(line.split(b":", 1) for line in header.split(b"\r\n")[1:] if b":" in line)
        accept = next((v.strip() for k, v in headers.items() if k.lower() == b"sec-websocket-accept"), b"")
        if accept != expected or b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise SteamClientError("Steam refused the debugger WebSocket")

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
            if length > 4 * 1024 * 1024:
                raise SteamClientError("Steam debugger response exceeds limit")
            if first & 0x0F == 8:
                raise SteamClientError("Steam debugger connection closed")
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
        raise SteamClientError("Steam library UI debug endpoint is unavailable") from exc
    for target in targets:
        if target.get("title") == "SharedJSContext" and target.get("webSocketDebuggerUrl"):
            return str(target["webSocketDebuggerUrl"])
    raise SteamClientError("Steam SharedJSContext is unavailable")


def evaluate(javascript: str):
    ws = _WebSocket(_shared_context_url())
    try:
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
                raise SteamClientError("Steam library UI rejected the request")
            return result.get("result", {}).get("value")
    finally:
        try:
            ws.socket.close()
        except OSError:
            pass

