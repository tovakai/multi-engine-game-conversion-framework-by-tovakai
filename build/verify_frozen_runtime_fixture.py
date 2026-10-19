"""Exercise the actual frozen GUI with a synthetic MV source and offline cache.

Requires a working DISPLAY or Xvfb/xvfb-run. By default the synthetic ARM64 ELF
checks routing, cache reuse and packaging only. --download-runtime opts into
official NW.js provisioning and a second conversion using its verified cache.
The MV source remains synthetic; neither mode tests actual gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile


def verify(executable: Path, receipt: Path, *, download_runtime=False):
    executable, receipt = executable.resolve(), receipt.resolve()
    with tempfile.TemporaryDirectory(prefix="megcfbt-frozen-runtime-") as temporary:
        work = Path(temporary)
        source, output, cache = work / "source", work / "output", work / "cache"
        for name, contents in {
            "www/js/rpg_core.js": 'Utils.RPGMAKER_VERSION = "1.6.1";',
            "www/data/System.json": '{"gameTitle":"Synthetic TLS Regression"}',
            "www/index.html": "<html>synthetic MV fixture</html>",
            "package.json": '{"main":"www/index.html"}',
        }.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        runtime = cache / "runtimes/nwjs/v0.117.0/nwjs-v0.117.0-linux-arm64"
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 183)
        if not download_runtime:
            runtime.mkdir(parents=True)
            (runtime / "nw").write_bytes(header)
            (runtime / "icudtl.dat").write_bytes(b"synthetic ICU resource")
            (runtime / "resources.pak").write_bytes(b"synthetic resource pack")
        output.mkdir()
        environment = dict(os.environ, RPGMFRAME_CACHE_DIR=str(cache))
        # Deliberately invalid TLS config proves that valid-cache conversion does
        # not resolve trust or initiate runtime downloads.
        if not download_runtime:
            environment["SSL_CERT_FILE"] = str(work / "absent-ca.pem")
        command = [str(executable), "--verify-gui-conversion", str(source),
                   "--output-dir", str(output), "--receipt", str(receipt)]
        if not environment.get("DISPLAY"):
            command = ["xvfb-run", "-a", *command]
        subprocess.run(command, env=environment, check=True, timeout=960 if download_runtime else 120)
        result = json.loads(receipt.read_text(encoding="utf-8"))
        if result.get("state") != "complete" or not result.get("frozen"):
            raise RuntimeError("Frozen fixture conversion did not complete")
        target = Path(result["output_path"])
        binary = (target / "nw").read_bytes()
        if binary[:6] != header[:6] or struct.unpack_from("<H", binary, 18)[0] != 183:
            raise RuntimeError("Frozen conversion changed target runtime architecture/content")
        if hashlib.sha256(binary).digest() != hashlib.sha256((runtime / "nw").read_bytes()).digest():
            raise RuntimeError("Packaged runtime differs from the verified cache")
        if not (target / "www/index.html").is_file() or not Path(result["package"]).is_file():
            raise RuntimeError("Frozen conversion did not package the fixture")
        after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        if before != after:
            raise RuntimeError("Frozen conversion modified source data")
        if download_runtime:
            if "Verified SHA256" not in result.get("log", ""):
                raise RuntimeError("Uncached conversion did not report NW.js checksum verification")
            # A second actual GUI conversion must succeed with trust resolution
            # deliberately made invalid: only a validated cache hit can do so.
            second_output = work / "output-reuse"
            second_output.mkdir()
            second_receipt = receipt.with_name(receipt.stem + "-reuse.json")
            reuse = [str(second_output) if value == str(output) else
                     str(second_receipt) if value == str(receipt) else value for value in command]
            environment["SSL_CERT_FILE"] = str(work / "absent-ca.pem")
            subprocess.run(reuse, env=environment, check=True, timeout=960)
            reused = json.loads(second_receipt.read_text(encoding="utf-8"))
            if reused.get("state") != "complete" or "Using cached NW.js" not in reused.get("log", ""):
                raise RuntimeError("Second frozen conversion did not reuse the verified cache")
            result["cache_reuse_checked"] = True
        result["synthetic_runtime"] = not download_runtime
        result["official_runtime_downloaded"] = download_runtime
        result["arm64_target_checked"] = True
        result["source_unchanged"] = True
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--download-runtime", action="store_true",
                        help="Opt in to real official NW.js provisioning and a second cached conversion")
    args = parser.parse_args()
    verify(args.executable, args.receipt, download_runtime=args.download_runtime)
