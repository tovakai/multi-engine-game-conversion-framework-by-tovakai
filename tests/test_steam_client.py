"""Local fake CDP only; tests never connect to the developer's Steam client."""
import base64
import hashlib
import json
import socket
import struct
import threading

import pytest

from megcfbt import steam_client as bridge


@pytest.mark.parametrize('url', ['ws://192.168.1.1:8080/devtools/page/x',
    'ws://localhost:8080/devtools/page/x', 'ws://127.0.0.1:8081/devtools/page/x',
    'ws://user@127.0.0.1:8080/devtools/page/x', 'wss://127.0.0.1:8080/devtools/page/x',
    'ws://127.0.0.1:8080/arbitrary', 'ws://127.0.0.1:8080/devtools/page/x?token=x'])
def test_unsafe_endpoints_rejected_before_connect(url, monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('unsafe connection'))
    with pytest.raises(bridge.Unavailable, match='unsafe'):
        bridge.WebSocket(url, 8080)


def test_websocket_cdp_transport_masking_fragmentation_ping_and_handshake_case():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    failures = []
    def server():
        try:
            connection, _ = listener.accept()
            with connection:
                request = b''
                while not request.endswith(b'\r\n\r\n'):
                    request += connection.recv(4096)
                key = next(line.split(b': ', 1)[1] for line in request.split(b'\r\n') if line.startswith(b'Sec-WebSocket-Key:'))
                accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
                connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: WebSocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
                def receive(count):
                    data = b''
                    while len(data) < count:
                        data += connection.recv(count - len(data))
                    return data
                first, second = receive(2)
                assert first == 0x81 and second & 0x80
                size = second & 127
                if size == 126:
                    size = struct.unpack('!H', receive(2))[0]
                mask = receive(4)
                request = json.loads(bytes(c ^ mask[i % 4] for i, c in enumerate(receive(size))))
                assert request['method'] == 'Runtime.evaluate'
                payload = json.dumps({'id': request['id'], 'result': {'result': {'value': True}}}).encode()
                connection.sendall(b'\x01' + bytes([10]) + payload[:10])
                connection.sendall(b'\x89\x02ok')
                connection.sendall(b'\x80' + bytes([len(payload) - 10]) + payload[10:])
                pong = receive(8)
                assert pong[0] == 0x8A and pong[1] == 0x82
        except BaseException as exc:
            failures.append(exc)
        finally:
            listener.close()
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    client = bridge.Client(bridge.WebSocket(f'ws://127.0.0.1:{port}/devtools/page/test', port), 'synthetic')
    try:
        assert client.evaluate('true') is True
    finally:
        client.close()
    thread.join(timeout=5)
    assert not thread.is_alive() and failures == []


def test_exact_custom_options_and_json_serialization(monkeypatch):
    client = bridge.Client(None, 'synthetic')
    options = "ENV='quotes'; $(not-executed) \"x\"\n"
    expressions = []
    def evaluate(expression):
        expressions.append(expression)
        return {'options': options}
    monkeypatch.setattr(client, 'evaluate', evaluate)
    assert client.read(413150) == options
    client.set(413150, '', options)
    assert json.dumps(options) in expressions[-1]
    assert 'GetLaunchOptionsForApp' not in bridge.OPTIONS_JS


@pytest.mark.parametrize('value', [True, 0, -1, 2**31, '413150'])
def test_invalid_appids_never_evaluated(value, monkeypatch):
    client = bridge.Client(None, 'synthetic')
    monkeypatch.setattr(client, 'evaluate', lambda expression: pytest.fail('invalid AppID used'))
    with pytest.raises(ValueError):
        client.read(value)


def test_conflict_and_unverified_write_fail_closed(monkeypatch):
    client = bridge.Client(None, 'synthetic')
    monkeypatch.setattr(client, 'evaluate', lambda expression: {'conflict': True})
    with pytest.raises(bridge.Changed):
        client.set(413150, '', 'new')
    monkeypatch.setattr(client, 'evaluate', lambda expression: {'options': 'other'})
    with pytest.raises(bridge.Unavailable):
        client.set(413150, '', 'new')


def test_no_endpoint_no_restart_or_configuration_edits(monkeypatch):
    class Missing:
        def __init__(self, host, port, **kwargs):
            assert host == '127.0.0.1' and port in {8080, 1337, 9222}
        def request(self, *args):
            raise ConnectionRefusedError('fixture')
        def close(self):
            pass
    monkeypatch.setattr(bridge.http.client, 'HTTPConnection', Missing)
    with pytest.raises(bridge.Unavailable, match='Automatic linking is unavailable'):
        bridge.connect()
