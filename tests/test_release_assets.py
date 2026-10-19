import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "release_asset_check", Path(__file__).resolve().parents[1] / "build/verify_release_assets.py")
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
VERSION, COMMIT = "0.1.1.2", "a" * 40


def fixtures(root, *, info_changes=None, wrong_architecture=False):
    for platform, machine in assets.PLATFORMS.items():
        windows = platform == "windows-x64"
        binary = bytearray(128)
        if windows:
            binary[:2] = b"MZ"
            struct.pack_into("<I", binary, 60, 64)
            binary[64:68] = b"PE\0\0"
            struct.pack_into("<H", binary, 68, machine)
        else:
            binary[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<H", binary, 18, 62 if wrong_architecture and machine == 183 else machine)
        info = dict(version=VERSION, release_version=VERSION, commit=COMMIT,
                    build_kind="release", tracked_changes=False, shallow=False, platform=platform)
        info.update(info_changes or {})
        files = {"BUILD.json": json.dumps(info).encode(),
                 "_internal/megcfbt/_build_info.json": json.dumps(info).encode(),
                 assets.APP + (".exe" if windows else ""): bytes(binary),
                 "LICENSE": b"license fixture", "THIRD_PARTY_NOTICES.md": b"notice fixture",
                 "RELEASE-NOTES.md": b"release fixture",
                 "_internal/certifi/cacert.pem": b"-----BEGIN CERTIFICATE-----\nfixture"}
        name = f"multi-engine-game-conversion-framework-by-tovakai-{VERSION}-{platform}." + ("zip" if windows else "tar.gz")
        path = root / name
        if windows:
            with zipfile.ZipFile(path, "w") as output:
                for member, data in files.items():
                    output.writestr(assets.APP + "/" + member, data)
        else:
            with tarfile.open(path, "w:gz") as output:
                for member, data in files.items():
                    entry = tarfile.TarInfo(assets.APP + "/" + member)
                    entry.size = len(data)
                    output.addfile(entry, io.BytesIO(data))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / f"SHA256SUMS-{platform}.txt").write_text(f"{digest}  {name}\n")


def test_valid_release_and_downloaded_roundtrip(tmp_path):
    fixtures(tmp_path)
    assert len(assets.verify(tmp_path, VERSION, COMMIT)) == 3
    for path in tmp_path.glob("SHA256SUMS-*.txt"):
        path.unlink()
    assert len(assets.verify(tmp_path, VERSION, COMMIT)) == 3


@pytest.mark.parametrize("changes", [{"commit": "b" * 40}, {"tracked_changes": True},
                                     {"build_kind": "development"}, {"version": VERSION + ".dev1"}])
def test_refuses_nonrelease_or_wrong_source(tmp_path, changes):
    fixtures(tmp_path, info_changes=changes)
    with pytest.raises(ValueError, match="exact clean tagged release"):
        assets.verify(tmp_path, VERSION, COMMIT)


def test_refuses_tampered_release_download(tmp_path):
    fixtures(tmp_path)
    path = next(tmp_path.glob("*.tar.gz"))
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum mismatch"):
        assets.verify(tmp_path, VERSION, COMMIT)


def test_refuses_wrong_architecture_even_with_matching_checksum(tmp_path):
    fixtures(tmp_path, wrong_architecture=True)
    with pytest.raises(ValueError, match="Wrong application architecture"):
        assets.verify(tmp_path, VERSION, COMMIT)
