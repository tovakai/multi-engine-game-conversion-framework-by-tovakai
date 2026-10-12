"""Static executable metadata; neither runs nor alters the game."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def inventory(path):
    data = path.read_bytes()
    architecture = "unknown"
    if data.startswith(b"\x7fELF"):
        machine, = struct.unpack_from("<H", data, 18)
        architecture = {183: "aarch64", 62: "x86_64"}.get(machine, str(machine))
    elif data.startswith(b"MZ"):
        pe_offset, = struct.unpack_from("<I", data, 60)
        machine, = struct.unpack_from("<H", data, pe_offset + 4)
        architecture = {0x8664: "x86_64", 0xAA64: "aarch64"}.get(machine, str(machine))
    paths = sorted(set(match.decode() for match in re.findall(
        rb"(?:drivers/gles3|modules/gridmap|modules/godotsteam)/[A-Za-z0-9_./-]+\.(?:cpp|h)", data)))
    versions = sorted(set(match.decode() for match in re.findall(
        rb"3\.[0-9]+\.[0-9]+\.(?:stable|dev|beta|rc)[A-Za-z0-9_.-]*", data)))
    return {"filename": path.name, "architecture": architecture,
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "version_strings": versions, "diagnostic_source_paths": paths,
            "scope": "Static strings do not establish which engine patches are present"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inventory(args.binary), indent=2))
