"""Reproduce the allowlisted runtime bundle from exact official upstream inputs.

No game content or Valve binary is read or redistributed by this script.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
RECIPE="godot-4.5-train45-native-arm64-v1"

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        while chunk:=f.read(8*1024**2):h.update(chunk)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates",type=Path,required=True)
    parser.add_argument("--godotsteam",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    assert digest(args.templates)=="375d83b661794f91746d2dec9b569a99d4d24f85a70c4ec0068aafb18b551d53", "Unexpected Godot templates archive"
    assert digest(args.godotsteam)=="7965a47fe05e32d9eac82ed5f1193b723649193cb67df9f47cbea4371ebef66e", "Unexpected GodotSteam archive"
    index=json.loads((ROOT/"rpgmframe/godot_extension_runtime_index.json").read_text(encoding="utf-8"))["recipes"][RECIPE]
    with zipfile.ZipFile(args.templates) as z:files={"godot.arm64":z.read("templates/linux_release.arm64")}
    with zipfile.ZipFile(args.godotsteam) as z:
        files["extensions/godotsteam/libgodotsteam.linux.template_release.arm64.so"]=z.read("addons/godotsteam/linuxarm64/libgodotsteam.linux.template_release.arm64.so")
    for name in index["files"]:
        if name not in files:files[name]=(Path(__file__).parent/name).read_bytes()
    assert {n:hashlib.sha256(b).hexdigest() for n,b in files.items()}==index["files"], "Runtime payload integrity mismatch"
    files["runtime.json"]=json.dumps({"recipe_id":RECIPE,"engine_version":"4.5.0","architecture":"aarch64",
        "capabilities":{"steam_api_provider":"steam-frame-installed","build_mode":"release"},"files":index["files"]},indent=2).encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.is_symlink():raise ValueError("Unsafe output symlink")
    with args.output.open("wb") as out,gzip.GzipFile(filename="",mode="wb",fileobj=out,mtime=0) as gz,tarfile.open(fileobj=gz,mode="w") as tar:
        for name,b in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(b);info.mode=0o755 if name=="godot.arm64" else 0o644;tar.addfile(info,io.BytesIO(b))
    assert digest(args.output)==index["sha256"], "Runtime archive checksum mismatch"
    print("VERIFIED_REPRODUCIBLE_RUNTIME",args.output)

if __name__=="__main__":main()
