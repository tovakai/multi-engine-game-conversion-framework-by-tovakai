"""Exercise the actual frozen GUI with a synthetic MV source and offline cache.

Requires a working DISPLAY or Xvfb/xvfb-run. The synthetic ARM64 ELF is an architecture fixture, not
a playable NW.js build; this checks routing, cache reuse and packaging only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile


def verify(executable: Path, receipt: Path):
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
        runtime.mkdir(parents=True)
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 183)
        (runtime / "nw").write_bytes(header)
        (runtime / "icudtl.dat").write_bytes(b"synthetic ICU resource")
        (runtime / "resources.pak").write_bytes(b"synthetic resource pack")
        output.mkdir()
        environment = dict(os.environ, RPGMFRAME_CACHE_DIR=str(cache))
        # Deliberately invalid TLS config proves that valid-cache conversion does
        # not resolve trust or initiate runtime downloads.
        environment["SSL_CERT_FILE"] = str(work / "absent-ca.pem")
        command = [str(executable), "--verify-gui-conversion", str(source),
                   "--output-dir", str(output), "--receipt", str(receipt)]
        if not environment.get("DISPLAY"):
            command = ["xvfb-run", "-a", *command]
        subprocess.run(command, env=environment, check=True, timeout=120)
        result = json.loads(receipt.read_text(encoding="utf-8"))
        if result.get("state") != "complete" or not result.get("frozen"):
            raise RuntimeError("Frozen fixture conversion did not complete")
        target = Path(result["output_path"])
        if (target / "nw").read_bytes() != header:
            raise RuntimeError("Frozen conversion changed target runtime architecture/content")
        if not (target / "www/index.html").is_file() or not Path(result["package"]).is_file():
            raise RuntimeError("Frozen conversion did not package the fixture")
        after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        if before != after:
            raise RuntimeError("Frozen conversion modified source data")
        result["synthetic_runtime"] = True
        result["arm64_target_checked"] = True
        result["source_unchanged"] = True
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    verify(args.executable, args.receipt)
