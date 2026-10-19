"""Inspect a trusted, host-native release libcrypto without starting its GUI.

This only creates an X509 trust store: no network connection or certificate
verification policy is modified. Run in a fresh process to avoid mixing already
loaded system and bundled OpenSSL libraries. Never load untrusted libraries.
"""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path


def inspect(library: Path, system_ca: Path | None = None):
    crypto = ctypes.CDLL(str(library.resolve()))
    def bind(name, restype, argtypes=()):
        function = getattr(crypto, name)
        function.restype = restype
        function.argtypes = argtypes
        return function
    version = bind("OpenSSL_version", ctypes.c_char_p, [ctypes.c_int])
    file_path = bind("X509_get_default_cert_file", ctypes.c_char_p)().decode()
    directory = bind("X509_get_default_cert_dir", ctypes.c_char_p)().decode()
    new_store = bind("X509_STORE_new", ctypes.c_void_p)
    defaults = bind("X509_STORE_set_default_paths", ctypes.c_int, [ctypes.c_void_p])
    objects = bind("X509_STORE_get0_objects", ctypes.c_void_p, [ctypes.c_void_p])
    count = bind("OPENSSL_sk_num", ctypes.c_int, [ctypes.c_void_p])
    free = bind("X509_STORE_free", None, [ctypes.c_void_p])
    store = new_store()
    if not store:
        raise RuntimeError("Could not allocate diagnostic X509 store")
    try:
        result = {"openssl": version(0).decode(),
                  "compiled_file": file_path, "compiled_file_exists": Path(file_path).exists(),
                  "compiled_directory": directory, "compiled_directory_exists": Path(directory).exists(),
                  "default_load_result": defaults(store), "default_trust_objects": count(objects(store))}
        if system_ca is not None:
            load = bind("X509_STORE_load_file", ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p])
            result["system_file_load_result"] = load(store, str(system_ca).encode())
            result["system_file_trust_objects"] = count(objects(store))
        return result
    finally:
        free(store)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--system-ca", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.library, args.system_ca), indent=2))
