"""Opt-in, credential-free TLS diagnostics for Python and frozen applications."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import ssl
import sys

from megcfbt.tls import resolve_context


def _path_status(value):
    if not value:
        return None
    path = Path(value)
    return {"path": value, "exists": path.exists(), "readable": os.access(path, os.R_OK)}


def report(*, smoke=False):
    paths = ssl.get_default_verify_paths()
    result = {
        "schema": "megcfbt.tls/v1",
        "python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION,
        "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False)),
        "pyinstaller_bundle": hasattr(sys, "_MEIPASS"),
        "verify_paths": paths._asdict(),
        "default_file": _path_status(paths.openssl_cafile),
        "default_directory": _path_status(paths.openssl_capath),
        # Report presence only: never enumerate environment or expose proxy URLs.
        "overrides": {key: key in os.environ for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")},
    }
    if sys.platform.startswith("linux"):
        try:
            import certifi
            bundled = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            bundled.load_verify_locations(cafile=certifi.where())
            result["bundled_ca"] = bundled.cert_store_stats()
        except (ImportError, OSError) as exc:
            result["bundled_ca"] = {"error_type": type(exc).__name__}
    try:
        context, source = resolve_context()
        result.update(trust_source=source, trust_objects=context.cert_store_stats(),
                      certificate_verification=context.verify_mode == ssl.CERT_REQUIRED,
                      hostname_verification=context.check_hostname)
    except OSError as exc:
        result.update(error=str(exc), error_type=type(exc).__name__)
        return result
    if smoke:
        # Exactly the NW.js provisioning path, including its existing headers.
        from rpgmframe.runtime import _download_text, _expected_sha256, _archive_name
        url = "https://dl.nwjs.io/v0.117.0/SHASUMS256.txt"
        try:
            statuses = []
            data = _download_text(url, status_callback=statuses.append)
            if statuses != [200]:
                raise RuntimeError("Checksum smoke did not receive HTTP 200")
            digest = _expected_sha256(data, _archive_name("0.117.0"))
            result["smoke"] = {"url": url, "status": statuses[0], "arm64_sha256": digest}
        except Exception as exc:
            result["smoke"] = {"url": url, "error": str(exc), "error_type": type(exc).__name__}
            cause = exc
            while cause.__cause__ is not None:
                cause = cause.__cause__
            reason = getattr(cause, "reason", cause)
            result["smoke"]["cause_type"] = type(reason).__name__
            if isinstance(reason, ssl.SSLCertVerificationError):
                result["smoke"]["verify_code"] = reason.verify_code
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls-diagnostics", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Contact only official NW.js checksum endpoint")
    args = parser.parse_args(argv)
    result = report(smoke=args.smoke)
    print(json.dumps(result, indent=2))
    return int("error" in result or "error" in result.get("smoke", {}))


if __name__ == "__main__":
    raise SystemExit(main())
