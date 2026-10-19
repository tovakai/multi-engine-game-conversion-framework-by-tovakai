"""Trust selection and actual OpenSSL handshakes, with no network sockets."""
import io
import json
import os
from pathlib import Path
import socket
import ssl
from types import SimpleNamespace
import urllib.error

import pytest

from megcfbt import tls, tls_diagnostics

FIXTURES = Path(__file__).parent / "fixtures/tls"


@pytest.fixture(autouse=True)
def clean_overrides(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(tls.sys, "platform", "linux")


def empty_defaults(monkeypatch):
    monkeypatch.setattr(tls.ssl, "create_default_context",
                        lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    monkeypatch.setattr(tls.ssl, "get_default_verify_paths", lambda: SimpleNamespace(capath=None))
    monkeypatch.setattr(tls, "SYSTEM_CA_FILES", ())
    monkeypatch.setattr(tls, "SYSTEM_CA_DIRS", ())


def handshake(context, hostname="localhost"):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(FIXTURES / "server.pem", FIXTURES / "server.key")
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = context.wrap_bio(client_in, client_out, server_hostname=hostname)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    completed = set()
    for _ in range(20):
        for name, peer in (("client", client), ("server", server)):
            if name not in completed:
                try:
                    peer.do_handshake()
                    completed.add(name)
                except ssl.SSLWantReadError:
                    pass
        server_in.write(client_out.read())
        client_in.write(server_out.read())
        if len(completed) == 2:
            return
    pytest.fail("In-memory TLS handshake did not complete")


def test_system_default_trust_is_preserved(monkeypatch):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=FIXTURES / "ca.pem")
    monkeypatch.setattr(tls.ssl, "create_default_context", lambda: context)
    result, source = tls.resolve_context()
    assert result is context and source == "openssl-default"
    handshake(result)


def test_explicit_ca_file(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(FIXTURES / "ca.pem"))
    context, source = tls.resolve_context()
    assert source == "explicit-override"
    handshake(context)
    with pytest.raises(ssl.SSLCertVerificationError, match="Hostname mismatch"):
        handshake(context, "wrong.example")


def test_explicit_ca_directory(tmp_path, monkeypatch):
    # Subject hash of the synthetic CA. This exercises OpenSSL's lazy capath.
    (tmp_path / "5334c74b.0").write_bytes((FIXTURES / "ca.pem").read_bytes())
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path))
    context, source = tls.resolve_context()
    assert source == "explicit-override"
    handshake(context)


@pytest.mark.parametrize("key", ["SSL_CERT_FILE", "SSL_CERT_DIR"])
@pytest.mark.parametrize("value", ["", "/nonexistent/megcfbt-ca"])
def test_invalid_override_fails_without_fallback(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(tls.CertificateConfigurationError, match=key):
        tls.resolve_context()


def test_invalid_ca_contents(tmp_path, monkeypatch):
    path = tmp_path / "not-ca.pem"
    path.write_text("invalid certificate")
    monkeypatch.setenv("SSL_CERT_FILE", str(path))
    with pytest.raises(tls.CertificateConfigurationError, match="SSL_CERT_FILE"):
        tls.resolve_context()


def test_missing_compiled_paths_use_os_bundle(monkeypatch):
    empty_defaults(monkeypatch)
    monkeypatch.setattr(tls, "SYSTEM_CA_FILES", ("/absent/ca.pem", str(FIXTURES / "ca.pem")))
    context, source = tls.resolve_context()
    assert source == "linux-system-file"
    handshake(context)


def test_os_hashed_directory_before_bundled_fallback(tmp_path, monkeypatch):
    empty_defaults(monkeypatch)
    (tmp_path / "5334c74b.0").write_bytes((FIXTURES / "ca.pem").read_bytes())
    monkeypatch.setattr(tls, "SYSTEM_CA_DIRS", (str(tmp_path),))
    context, source = tls.resolve_context()
    assert source == "linux-system-directory"
    handshake(context)


def test_bundled_fallback_preserves_verification(monkeypatch):
    certifi = pytest.importorskip("certifi")
    empty_defaults(monkeypatch)
    monkeypatch.setattr(certifi, "where", lambda: str(FIXTURES / "ca.pem"))
    context, source = tls.resolve_context()
    assert source == "bundled-mozilla"
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    handshake(context)
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(context, "untrusted.example")


@pytest.mark.parametrize("contents", [None, b"broken PEM", b""])
def test_missing_or_invalid_fallback(tmp_path, monkeypatch, contents):
    certifi = pytest.importorskip("certifi")
    empty_defaults(monkeypatch)
    path = tmp_path / "cacert.pem"
    if contents is not None:
        path.write_bytes(contents)
    monkeypatch.setattr(certifi, "where", lambda: str(path))
    with pytest.raises(tls.CertificateConfigurationError, match="bundled CA resource"):
        tls.resolve_context()


def test_untrusted_chain_rejected():
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))


def test_inaccessible_explicit_file_fails(tmp_path, monkeypatch):
    path = tmp_path / "unreadable.pem"
    path.write_bytes((FIXTURES / "ca.pem").read_bytes())
    path.chmod(0)
    monkeypatch.setenv("SSL_CERT_FILE", str(path))
    try:
        if os.access(path, os.R_OK):
            pytest.skip("Current account bypasses file permissions")
        with pytest.raises(tls.CertificateConfigurationError, match="SSL_CERT_FILE"):
            tls.resolve_context()
    finally:
        path.chmod(0o600)


def test_missing_fallback_dependency(monkeypatch):
    empty_defaults(monkeypatch)
    monkeypatch.setitem(tls.sys.modules, "certifi", None)
    with pytest.raises(tls.CertificateConfigurationError, match="bundled CA resource"):
        tls.resolve_context()


def test_inaccessible_system_material_uses_packaged_roots(monkeypatch):
    certifi = pytest.importorskip("certifi")
    empty_defaults(monkeypatch)
    monkeypatch.setattr(tls, "SYSTEM_CA_FILES", ("/unreadable/ca.pem",))
    monkeypatch.setattr(certifi, "where", lambda: str(FIXTURES / "ca.pem"))
    original = ssl.SSLContext.load_verify_locations
    def load(context, cafile=None, *args, **kwargs):
        if cafile == "/unreadable/ca.pem":
            raise PermissionError("synthetic denied system bundle")
        return original(context, cafile, *args, **kwargs)
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", load)
    context, source = tls.resolve_context()
    assert source == "bundled-mozilla"
    handshake(context)


@pytest.mark.parametrize("error, expected", [
    (urllib.error.HTTPError("https://example.invalid", 403, "Forbidden", {}, None), "HTTP 403"),
    (urllib.error.HTTPError("https://example.invalid", 404, "Missing", {}, None), "HTTP 404"),
    (urllib.error.HTTPError("https://example.invalid", 503, "Unavailable", {}, None), "HTTP 503"),
    (urllib.error.URLError(socket.gaierror(-2, "DNS")), "DNS name resolution"),
    (urllib.error.URLError(TimeoutError()), "Network timeout"),
    (urllib.error.URLError(ssl.SSLCertVerificationError(1, "invalid")), "server identity"),
])
def test_network_error_categories(monkeypatch, error, expected):
    # This test isolates error classification from host trust configuration.
    # In particular, Windows need not install Linux's optional CA dependency.
    monkeypatch.setattr(tls, "resolve_context", lambda: (
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), "synthetic-test-context"))
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(tls.urllib.request, "urlopen", fail)
    with pytest.raises(OSError, match=expected):
        tls.open_url("https://example.invalid/runtime", timeout=30)


def test_no_tls_retry_or_proxy_mutation(monkeypatch):
    monkeypatch.setattr(tls, "resolve_context", lambda: (
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), "synthetic-test-context"))
    calls = []
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@private.example:8080")
    def fail(request, **kwargs):
        calls.append(kwargs)
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "untrusted"))
    monkeypatch.setattr(tls.urllib.request, "urlopen", fail)
    with pytest.raises(OSError):
        tls.open_url("https://example.invalid/runtime", timeout=60)
    assert len(calls) == 1 and calls[0]["timeout"] == 60
    assert calls[0]["context"].check_hostname
    assert os.environ["HTTPS_PROXY"] == "http://user:secret@private.example:8080"


def test_windows_urllib_call_is_unchanged(monkeypatch):
    monkeypatch.setattr(tls.sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(tls.urllib.request, "urlopen", lambda *a, **k: calls.append(k))
    tls.open_url("https://example.invalid", timeout=15)
    assert calls == [{"timeout": 15}]


def test_diagnostics_omit_sensitive_environment(monkeypatch):
    monkeypatch.setattr(tls_diagnostics, "resolve_context", lambda: (
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), "synthetic-test-context"))
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@private.example")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sensitive")
    value = json.dumps(tls_diagnostics.report())
    assert "secret" not in value and "sensitive" not in value and "private.example" not in value
    assert '"hostname_verification": true' in value
