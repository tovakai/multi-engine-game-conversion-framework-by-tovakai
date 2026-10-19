"""Per-request Linux trust resolution; never retry a failed TLS handshake."""
from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


# OpenSSL in a frozen app retains the build distribution's compiled paths.
# These are OS-managed bundles, not certificates shipped with the application.
SYSTEM_CA_FILES = (
    "/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "/etc/ssl/ca-bundle.pem",
)
SYSTEM_CA_DIRS = ("/etc/ssl/certs", "/etc/pki/tls/certs")


class CertificateConfigurationError(OSError):
    """Local trust configuration is unusable; downloading must stop."""


def _usable_directory(path: str) -> bool:
    """OpenSSL capath is lazy and requires rehashed PEM files (hash.N)."""
    try:
        for entry in Path(path).iterdir():
            if re.fullmatch(r"[0-9a-fA-F]{8}\.\d+", entry.name):
                probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                try:
                    probe.load_verify_locations(cafile=str(entry))
                    if probe.cert_store_stats()["x509_ca"]:
                        return True
                except (OSError, ssl.SSLError):
                    continue
    except OSError:
        pass
    return False


def resolve_context() -> tuple[ssl.SSLContext, str]:
    """Prefer defaults, then Linux system roots, then packaged Mozilla roots.

    Explicit overrides are validated before OpenSSL can silently ignore them.
    They never trigger extra system roots or a bundled fallback. On Windows,
    Python's native certificate-store behavior is unchanged.
    """
    if not sys.platform.startswith("linux"):
        return ssl.create_default_context(), "platform-default"

    overrides = {key: os.environ[key] for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")
                 if key in os.environ}
    for key, value in overrides.items():
        if not value:
            raise CertificateConfigurationError(f"Invalid {key}: value is empty")
        if key == "SSL_CERT_FILE":
            probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            try:
                probe.load_verify_locations(cafile=value)
                if not probe.cert_store_stats()["x509_ca"]:
                    raise ValueError("no CA certificates")
            except (OSError, ValueError) as exc:
                raise CertificateConfigurationError(
                    f"Invalid {key}: expected a readable PEM CA bundle ({type(exc).__name__})"
                ) from exc
        elif not all(_usable_directory(part) for part in value.split(os.pathsep)):
            raise CertificateConfigurationError(
                f"Invalid {key}: expected a readable OpenSSL hashed CA directory; "
                "check the directory and run openssl rehash if necessary"
            )

    try:
        context = ssl.create_default_context()
    except OSError as exc:
        if overrides:
            raise CertificateConfigurationError("Could not load explicitly configured certificate trust") from exc
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if overrides:
        return context, "explicit-override"
    defaults = ssl.get_default_verify_paths()
    if context.cert_store_stats()["x509_ca"] or (
        defaults.capath and _usable_directory(defaults.capath)
    ):
        return context, "openssl-default"

    for path in SYSTEM_CA_FILES:
        try:
            context.load_verify_locations(cafile=path)
            if context.cert_store_stats()["x509_ca"]:
                return context, "linux-system-file"
        except (OSError, ssl.SSLError):
            continue
    for path in SYSTEM_CA_DIRS:
        if _usable_directory(path):
            context.load_verify_locations(capath=path)
            return context, "linux-system-directory"

    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
        if not context.cert_store_stats()["x509_ca"]:
            raise ValueError("no CA certificates")
    except (ImportError, OSError, ValueError) as exc:
        raise CertificateConfigurationError(
            "No usable system CA certificates and the bundled CA resource is unavailable "
            "or invalid. Install the operating system ca-certificates package, repair "
            "the application installation, or configure SSL_CERT_FILE/SSL_CERT_DIR."
        ) from exc
    return context, "bundled-mozilla"


def failure_message(url: str, exc: BaseException) -> str:
    """Classify failures without disclosing URL credentials, queries or proxies."""
    host = urllib.parse.urlsplit(url).hostname or "download host"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(exc, CertificateConfigurationError):
        return str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} from {host}; the server rejected the download"
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (f"TLS certificate validation failed for {host}: server identity could not "
                "be verified. Check system CA certificates, SSL_CERT_FILE/SSL_CERT_DIR "
                "and any managed network certificate configuration.")
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return f"Network timeout while downloading from {host}; retry when connectivity is restored"
    if isinstance(reason, socket.gaierror):
        return f"Could not reach {host}: DNS name resolution failed"
    if isinstance(reason, ssl.SSLError):
        return f"TLS connection failed for {host} ({type(reason).__name__})"
    return f"Could not complete download from {host} ({type(reason).__name__}); check network connectivity"


def open_url(request, *, timeout):
    """Keep urllib headers, redirects, proxies and timeouts; scope TLS to request."""
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    try:
        if sys.platform.startswith("linux") and urllib.parse.urlsplit(url).scheme == "https":
            context, _ = resolve_context()
            return urllib.request.urlopen(request, timeout=timeout, context=context)
        return urllib.request.urlopen(request, timeout=timeout)
    except (OSError, urllib.error.URLError) as exc:
        if isinstance(exc, CertificateConfigurationError):
            raise
        raise OSError(failure_message(url, exc)) from exc
