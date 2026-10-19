"""Validate exact tagged converter assets before draft publication and upload verification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile
import zipfile

APP = "Multi-Engine Game Conversion Framework by tovakai"
PLATFORMS = {"linux-aarch64": 183, "linux-x64": 62, "windows-x64": 0x8664}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(directory: Path, version: str, commit: str):
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid release version or commit")
    combined = directory / "SHA256SUMS.txt"
    expected_sums = {}
    if combined.exists():
        for line in combined.read_text().splitlines():
            digest, name = line.split()
            if name in expected_sums:
                raise ValueError("Duplicate release checksum entry")
            expected_sums[name] = digest
    verified = []
    for platform, machine in PLATFORMS.items():
        suffix = "zip" if platform == "windows-x64" else "tar.gz"
        name = f"multi-engine-game-conversion-framework-by-tovakai-{version}-{platform}.{suffix}"
        path = directory / name
        digest = sha256(path)
        if expected_sums:
            expected = expected_sums.get(name)
        else:
            parts = (directory / f"SHA256SUMS-{platform}.txt").read_text().split()
            if len(parts) != 2 or parts[1] != name:
                raise ValueError("Unexpected platform checksum entry")
            expected = parts[0]
        if digest != expected:
            raise ValueError(f"Release checksum mismatch: {name}")
        archive = zipfile.ZipFile(path) if suffix == "zip" else tarfile.open(path, "r:gz")
        with archive:
            def read(relative):
                member = APP + "/" + relative
                if suffix == "zip":
                    return archive.open(member)
                result = archive.extractfile(member)
                if result is None:
                    raise ValueError(f"Missing release member: {member}")
                return result
            def metadata(relative):
                with read(relative) as stream:
                    return json.load(stream)
            info = metadata("BUILD.json")
            embedded = metadata("_internal/megcfbt/_build_info.json")
            required = {"version": version, "release_version": version, "commit": commit,
                        "build_kind": "release", "tracked_changes": False,
                        "shallow": False, "platform": platform}
            if any(info.get(key) != value or embedded.get(key) != value for key, value in required.items()):
                raise ValueError(f"Archive is not the exact clean tagged release: {name}")
            for relative in ("LICENSE", "THIRD_PARTY_NOTICES.md", "RELEASE-NOTES.md"):
                with read(relative) as stream:
                    if not stream.read(1):
                        raise ValueError(f"Empty release notice: {relative}")
            binary = APP + (".exe" if suffix == "zip" else "")
            with read(binary) as stream:
                header = stream.read(64)
                if suffix == "zip":
                    if header[:2] != b"MZ":
                        raise ValueError("Windows asset is not PE")
                    stream.seek(struct.unpack_from("<I", header, 60)[0])
                    signature = stream.read(6)
                    valid = signature[:4] == b"PE\0\0" and struct.unpack_from("<H", signature, 4)[0] == machine
                else:
                    valid = header[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", header, 18)[0] == machine
                if not valid:
                    raise ValueError(f"Wrong application architecture: {name}")
            if suffix != "zip":
                with read("_internal/certifi/cacert.pem") as stream:
                    if b"BEGIN CERTIFICATE" not in stream.read():
                        raise ValueError("Packaged Linux CA resource is missing")
        verified.append(f"{digest}  {name}\n")
    if expected_sums and set(expected_sums) != {line.split()[1] for line in verified}:
        raise ValueError("Unexpected release checksum inventory")
    combined.write_text("".join(verified), encoding="utf-8")
    return [line.split()[1] for line in verified]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.version, args.commit), indent=2))
