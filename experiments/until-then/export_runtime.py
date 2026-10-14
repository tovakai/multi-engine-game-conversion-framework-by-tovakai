"""Export the tested open-source runtime; exclude all game/vendor SDK content."""
from pathlib import Path
import hashlib, json, shutil, tarfile, io

base = Path.home() / ".cache/megcfbt/research/until-then"
output = base / "portable-runtime-v1"
output.mkdir(exist_ok=True)
recipe = "godot-4.1.4-until-then-native-arm64-v1"
archive_name = recipe + ".tar.gz"
sources = {
    "godot.arm64": "godot-4.1.4/bin/godot.linuxbsd.template_release.arm64",
    "extensions/internal/libinternal.so": "native/bin/libuntilthen.linux.template_release.arm64.so",
    "extensions/jsonutils/libjsonutils.so": "native/bin/libuntilthen.linux.template_release.arm64.so",
    "extensions/inkcpp/libinkcpp.so": "inkcpp/bin/libinkcpp.megcfbt.arm64.so",
    "extensions/threen/libthreen.so": "threen/bin/libthreen.megcfbt.arm64.so",
    "extensions/godotsteam/libgodotsteam.so": "steam-4.1/bin/libgodotsteam.megcfbt.arm64.so",
    "extensions/fmod/libfmod.release.so": "fmod-for-godot/addons/FMOD/native/bin/libfmod.megcfbt.arm64.so",
    "licenses/LICENSE-Godot.txt": "godot-4.1.4/LICENSE.txt",
    "licenses/COPYRIGHT-Godot.txt": "godot-4.1.4/COPYRIGHT.txt",
    "licenses/LICENSE-GodotCpp.md": "godot-cpp/LICENSE.md",
    "licenses/LICENSE-InkCPP.txt": "inkcpp/LICENSE.txt",
    "licenses/LICENSE-Threen.md": "threen/LICENSE.md",
    "licenses/LICENSE-FMOD-binding.txt": "fmod-for-godot/LICENSE",
    "licenses/LICENSE-GodotSteam.txt": "steam-4.1/LICENSE.txt",
}
for name, source in sources.items():
    target = output / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base / source, target)
# Only independently authored converter sources, never extracted game scripts.
own = base / "portable-runtime-sources"
for path in own.rglob("*"):
    if path.is_file():
        name = "sources/" + path.relative_to(own).as_posix()
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        sources[name] = "portable-runtime-sources/" + path.relative_to(own).as_posix()
(output / "NOTICE.txt").write_text(
    "Experimental Until Then native Godot runtime. Opening gameplay, audio, input, "
    "save/reload and normal exit tested on Steam Frame. Full-game coverage, playtime "
    "and achievements remain unverified.\n"
    "Godot, GodotCpp, InkCPP, Threen, GodotSteam and FMOD binding licenses are in licenses/. "
    "Converter-owned replacement sources are under the converter GPL-3.0-only license.\n"
    "FMOD SDK, FMOD vendor runtime libraries, Steam SDK headers, Steam runtime libraries "
    "and all game data are excluded. Supply the licensed FMOD 2.02.35 Linux SDK yourself; "
    "the genuine Steam API is resolved from the running Frame installation.\n"
    "The nlohmann JSON 3.10.4 MIT license is included with the replacement sources.\n")
sources["NOTICE.txt"] = None
files = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in sources}
manifest = {"recipe_id": recipe, "architecture": "aarch64", "engine_version": "4.1.4",
    "capabilities": {"resource_overlay_before_extensions": True, "extension_symbols": "isolated",
        "fmod_abi": "2.02", "steam_api_provider": "steam-frame-installed"}, "files": files,
    "source_refs": {"godot": "fe0e8e55752b0c2e64997025717b491703e0f8ad",
        "godot_cpp": "4b0ee133274d67687b6003b8d5fdaf7b79cf4921",
        "inkcpp": "fe1b761f47ecd1c04d2dc366d3d817957f4eb608",
        "threen": "4ee5588cb8ee203048ab66c89377e29e78ab82a3",
        "fmod_binding": "2046fb9ef051c4e3936f363d01ba5784052a787f",
        "godotsteam": "84ece1a226b8fd099333940e7a3b8367efb59370",
        "steam_headers": "5b89db940e0ebe3a137a6009a3589232fe084c09", "json": "3.10.4"}}
(output / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
names = sorted([*files, "runtime.json"])
archive = base / archive_name
with tarfile.open(archive, "w:gz") as tar:
    for name in names:
        data = (output / name).read_bytes()
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o755 if name == "godot.arm64" else 0o644
        tar.addfile(info, io.BytesIO(data))
index = {"recipes": {recipe: {"recipe_id": recipe, "executable": "godot.arm64",
    "archive_name": archive_name, "archive_files": names, "files": files,
    "url": "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/runtime-until-then-arm64-v1/" + archive_name,
    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "status": "experimental-opening-gameplay-verified"}}}
(base / "portable-runtime-index.json").write_text(json.dumps(index, indent=2) + "\n")
print("PORTABLE_RUNTIME_EXPORTED", archive, archive.stat().st_size, flush=True)
