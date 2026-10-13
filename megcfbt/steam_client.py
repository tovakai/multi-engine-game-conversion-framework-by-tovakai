"""Narrow live Steam launch-options bridge over an EXISTING loopback CEF endpoint.

No debugger setup, process injection, Steam restarts, binary/config edits or
third-party dependencies. Only fixed, JSON-parameterized SteamClient operations.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import socket
import struct
import time
from urllib.parse import urlsplit


class Unavailable(ValueError):
    pass


class Changed(ValueError):
    pass


def valid_appid(value):
    if type(value) is not int or not 0 < value < 2**31:
        raise ValueError('Invalid original Steam AppID')
    return value


class WebSocket:
    """Minimal RFC6455 client for bounded local CDP JSON messages."""
    def __init__(self, url, port):
        parsed = urlsplit(url)
        if (parsed.scheme != 'ws' or parsed.hostname != '127.0.0.1'
                or parsed.port != port or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or not re.fullmatch(r'/devtools/page/[A-Za-z0-9-]+', parsed.path)):
            raise Unavailable('Steam CEF returned an unsafe debugging endpoint')
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=5)
        self.socket.settimeout(25)
        self.buffer = b''
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        try:
            self.socket.sendall((f'GET {parsed.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                'Sec-WebSocket-Version: 13\r\n\r\n').encode('ascii'))
            header = b''
            while b'\r\n\r\n' not in header:
                chunk = self.socket.recv(4096)
                if not chunk or len(header) > 16384:
                    raise Unavailable('Invalid Steam CEF websocket handshake')
                header += chunk
            raw, self.buffer = header.split(b'\r\n\r\n', 1)
            lines = raw.decode('ascii').split('\r\n')
            headers = {name.lower(): value for name, value in
                       (line.split(':', 1) for line in lines[1:] if ':' in line)}
            expected = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
            if (' 101 ' not in lines[0] or headers.get('sec-websocket-accept', '').strip() != expected
                    or headers.get('upgrade', '').strip().lower() != 'websocket'):
                raise Unavailable('Steam CEF refused websocket access')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.socket.close()

    def read(self, count):
        while len(self.buffer) < count:
            chunk = self.socket.recv(min(65536, count - len(self.buffer)))
            if not chunk:
                raise Unavailable('Steam CEF connection closed')
            self.buffer += chunk
        result, self.buffer = self.buffer[:count], self.buffer[count:]
        return result

    def send(self, payload, opcode=1):
        size = len(payload)
        header = bytes([0x80 | opcode])
        header += (bytes([0x80 | size]) if size < 126 else
                   bytes([0xFE]) + struct.pack('!H', size) if size < 65536 else
                   bytes([0xFF]) + struct.pack('!Q', size))
        mask = os.urandom(4)
        self.socket.sendall(header + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def receive(self):
        result = bytearray()
        started = False
        while True:
            first, second = self.read(2)
            opcode, size = first & 15, second & 127
            if first & 0x70 or second & 0x80:
                raise Unavailable('Unsupported Steam websocket frame')
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            if size > 2 * 1024 * 1024 or len(result) + size > 2 * 1024 * 1024:
                raise Unavailable('Steam CEF response is too large')
            payload = self.read(size)
            if opcode == 8:
                raise Unavailable('Steam CEF closed websocket')
            if opcode == 9:
                self.send(payload, 10)
                continue
            if opcode == 10:
                continue
            if (opcode == 1 and not started) or (opcode == 0 and started):
                started = True
                result.extend(payload)
            else:
                raise Unavailable('Unsupported Steam websocket message')
            if first & 0x80:
                return json.loads(result.decode('utf-8'))


# RegisterForAppDetails yields the user's strLaunchOptions; GetLaunchOptionsForApp
# yields game-defined launch choices and must never be used as a backup.
OPTIONS_JS = r'''(async (appId, mode, expected, desired) => {
 const apps = globalThis.SteamClient?.Apps;
 if (typeof apps?.SetAppLaunchOptions !== 'function' ||
     typeof apps?.RegisterForAppDetails !== 'function') throw new Error('Steam launch-options API unavailable');
 const read = () => new Promise((resolve, reject) => {
   let handle, settled = false;
   const cleanup = () => { if (handle) {
     if (typeof handle.unregister === 'function') handle.unregister();
     else if (typeof handle === 'function') handle();
   }};
   const timer = setTimeout(() => { settled = true; cleanup(); reject(new Error('Steam app details timed out')); }, 4000);
   handle = apps.RegisterForAppDetails(appId, details => {
     if (settled || typeof details?.strLaunchOptions !== 'string') return;
     const id = details.unAppID ?? details.nAppID ?? details.appid;
     settled = true; clearTimeout(timer);
     if (id !== undefined && Number(id) !== appId) { cleanup(); reject(new Error('Steam returned another AppID')); return; }
     cleanup(); resolve(details.strLaunchOptions);
   });
   if (settled) cleanup();
 });
 const current = await read();
 if (mode === 'read') return {options: current};
 if (current !== expected) return {conflict: true};
 if (current !== desired) await apps.SetAppLaunchOptions(appId, desired);
 for (let attempt = 0; attempt < 12; attempt++) {
   const options = await read();
   if (options === desired) return {options};
   await new Promise(resolve => setTimeout(resolve, 150));
 }
 throw new Error('Steam launch-options readback did not match');
})'''


class Client:
    def __init__(self, socket_, endpoint):
        self.socket, self.endpoint, self.sequence = socket_, endpoint, 0

    def close(self):
        self.socket.close()

    def evaluate(self, expression):
        self.sequence += 1
        self.socket.send(json.dumps({'id': self.sequence, 'method': 'Runtime.evaluate',
            'params': {'expression': expression, 'awaitPromise': True, 'returnByValue': True,
                       'timeout': 20000}}).encode('utf-8'))
        deadline = time.monotonic() + 25
        while True:
            if time.monotonic() > deadline:
                raise Unavailable('Steam live API response timed out')
            result = self.socket.receive()
            if not isinstance(result, dict):
                raise Unavailable('Invalid Steam CEF response')
            if result.get('id') != self.sequence:
                continue
            value = result.get('result', {})
            if result.get('error') or value.get('exceptionDetails'):
                raise Unavailable('Steam live API failed; no verified launch-option result')
            return value.get('result', {}).get('value')

    def read(self, number):
        value = self.evaluate(OPTIONS_JS + '(' + json.dumps([valid_appid(number), 'read', None, None])[1:-1] + ')')
        if not isinstance(value, dict) or not isinstance(value.get('options'), str) or len(value['options']) > 65536:
            raise Unavailable('Steam did not return its custom launch-option string')
        return value['options']

    def set(self, number, expected, desired):
        valid_appid(number)
        if not all(isinstance(s, str) and len(s) <= 65536 for s in (expected, desired)):
            raise ValueError('Invalid launch-option string')
        value = self.evaluate(OPTIONS_JS + '(' + json.dumps([number, 'write', expected, desired])[1:-1] + ')')
        if isinstance(value, dict) and value.get('conflict'):
            raise Changed('Steam launch options changed; unrelated user settings were not overwritten')
        if not isinstance(value, dict) or value.get('options') != desired:
            raise Unavailable('Steam launch-option write could not be verified; recovery record retained')


def connect():
    for port in (8080, 1337, 9222):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        try:
            connection.request('GET', '/json/list')
            response = connection.getresponse()
            payload = response.read(2 * 1024 * 1024 + 1)
            if response.status != 200 or len(payload) > 2 * 1024 * 1024:
                continue
            targets = json.loads(payload)
            if not isinstance(targets, list):
                continue
            for target in targets:
                if not isinstance(target, dict) or target.get('type') != 'page':
                    continue
                if not isinstance(target.get('url'), str) or not isinstance(target.get('webSocketDebuggerUrl'), str):
                    continue
                url = urlsplit(target['url'])
                if url.hostname != 'steamloopback.host' or target.get('title') != 'SharedJSContext':
                    continue
                client = Client(WebSocket(target.get('webSocketDebuggerUrl', ''), port), f'127.0.0.1:{port}')
                try:
                    ready = client.evaluate("typeof SteamClient?.Apps?.SetAppLaunchOptions === 'function' && typeof SteamClient?.Apps?.RegisterForAppDetails === 'function'")
                    if ready is True:
                        return client
                except (OSError, ValueError):
                    pass
                client.close()
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    raise Unavailable('No usable existing loopback Steam CEF interface. Automatic linking is unavailable on this client. Keep Steam running and use the non-Steam option; debugger setup/restarts are not performed by this installer.')


if __name__ == '__main__':
    import sys
    client = connect()
    try:
        options = client.read(valid_appid(int(sys.argv[1])))
        print(json.dumps({'endpoint': client.endpoint, 'appid': int(sys.argv[1]),
            'options_length': len(options), 'options_sha256': hashlib.sha256(options.encode()).hexdigest()}))
    finally:
        client.close()
