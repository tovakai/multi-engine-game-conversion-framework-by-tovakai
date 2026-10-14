"""Audited experimental Until Then native Godot conversion profile."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot_overlay import extension, read_resource, write_pack

PROFILE = "experimental-until-then-build23785927-native-v1"
RUNTIME_KIND = "godot-until-then"
RECIPE = "godot-4.1.4-until-then-native-arm64-v1"
APPID = 1574820
FMOD_FILENAME = "fmodstudioapi20235linux.tar.gz"
FMOD_SHA256 = "855381248a85b6457b96090c9f9c0b070a51f10be6bf07b4a6456a12f8aff807"
FMOD_SIZE = 75069383
PACK_SHA256 = "303f6f2bba7e912b9868437ec75811c7a46c657e999f8032a6a0823b867b6ef0"
PACK_SIZE = 3488040345
SOURCE_LIBRARIES = {
    "internal.dll": "dc8f23a667668fa288617ae196644b4f47b105e2be48930437a39959bfae0ac6",
    "jsonutils.dll": "868980d3b72e1db996f4b50324fbc37f1cd1d37a19ef6a206a72b693d59d0342",
    "inkcpp.dll": "c54325d4e166c29bc47635edab1cab46699fddd22d47583d91ef092389777dc2",
    "threen.dll": "ab6b75f4272955f78fa0c0e28472c20b6943547106d9d1493c71c2711d1a0fd0",
    "godotsteam.dll": "994107bd9e54686174da667d839b16d2beef98ae36e65564a7419393d8f807cd",
    "fmod.release.dll": "232b739836e13038c1bc3c6f30ae172d7e675fb46b8050114cc7890a40dc47a4",
}
LIBRARIES = {
    "internal": ("internal_library_init", "libinternal.so"),
    "jsonutils": ("jsonutils_library_init", "libjsonutils.so"),
    "inkcpp": ("inkcpp_library_init", "libinkcpp.so"),
    "threen": ("threen_library_init", "libthreen.so"),
    "godotsteam": ("godotsteam_init", "libgodotsteam.so"),
    "fmod": ("fmod_library_init", "libfmod.release.so"),
}
THUMBNAIL_SCRIPT = "ui/components/Game/SceneView/SceneView.gd"
OLD_LOADER_CALL = b'ResourceLoader.load_threaded_request(_path, "", false, ResourceLoader.CACHE_MODE_REUSE, true)'
NEW_LOADER_CALL = b'ResourceLoader.load_threaded_request(_path, "", false, ResourceLoader.CACHE_MODE_REUSE)'


def digest(path: Path, progress=None) -> str:
    hashed = hashlib.sha256()
    total = path.stat().st_size
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024**2):
            hashed.update(chunk)
            count += len(chunk)
            if progress:
                progress(count, total)
    return hashed.hexdigest()


def candidate(pack, root: Path) -> bool:
    """Fast inspection hint only; the complete PCK hash gates every conversion."""
    if (pack.embedded or pack.version != "4.1.4" or pack.pack_format != 2
            or pack.path.stat().st_size != PACK_SIZE or pack.path.is_symlink()):
        return False
    try:
        return all((root / name).is_file() and not (root / name).is_symlink()
                   and (root / name).stat().st_size <= 64 * 1024**2
                   and digest(root / name) == expected
                   for name, expected in SOURCE_LIBRARIES.items())
    except OSError:
        return False


def validate_source(pack, root: Path, progress=None):
    from megcfbt.steam_context import verified_source_identity
    if not candidate(pack, root) or digest(pack.path, progress) != PACK_SHA256:
        raise ValueError("Until Then source does not match the audited Steam build 23785927. This update requires a new compatibility profile.")
    # Hash-gated profile identifies a release, never ownership. Sidecars cannot
    # select another AppID; an exact source manifest may add genuine provenance.
    return verified_source_identity(root, APPID)


def validate_fmod_sdk(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size != FMOD_SIZE or digest(path) != FMOD_SHA256:
        raise ValueError("Until Then requires the checksum-verified FMOD Studio API 2.02.35 Linux SDK archive (not Celeste's 2.03.15 SDK).")
    return path


def find_fmod_sdk():
    from megcfbt.fmod_sdk import remembered_sdk
    selected = os.environ.get("MEGCFBT_UNTIL_THEN_FMOD_SDK")
    if selected:
        return validate_fmod_sdk(Path(selected))
    for path in (remembered_sdk(), Path.home() / "Downloads" / FMOD_FILENAME):
        if path is not None:
            try:
                return validate_fmod_sdk(path)
            except (OSError, ValueError):
                continue
    return None


def extension_directory(name):
    return "addons/fmod/native/linux" if name == "fmod" else f"addons/{name}/linux"


def install_overlay(pack: Path, game: Path):
    files = {}
    for name, (symbol, library) in LIBRARIES.items():
        dependencies = ("addons/fmod/native/linux/libfmod.so", "addons/fmod/native/linux/libfmodstudio.so") if name == "fmod" else ()
        # The genuine Steam API is resolved from the installed native client by
        # LD_LIBRARY_PATH, rather than bundling a proprietary Steam library.
        files[f"addons/{name}/{name}.gdextension"] = extension(
            symbol, extension_directory(name) + "/" + library, dependencies)
    original = read_resource(pack, THUMBNAIL_SCRIPT)
    if original.count(OLD_LOADER_CALL) != 1:
        raise ValueError("Unexpected Until Then thumbnail loader; refusing an unverified patch")
    files[THUMBNAIL_SCRIPT] = original.replace(OLD_LOADER_CALL, NEW_LOADER_CALL)
    write_pack(game / "untilthen-native-overlay.pck", files)
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def install_owner_fmod(sdk: Path, game: Path):
    target = game / extension_directory("fmod")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(sdk) as archive:
        for component, name in (("core", "fmod"), ("studio", "fmodstudio")):
            member = archive.getmember(f"fmodstudioapi20235linux/api/{component}/lib/arm64/lib{name}.so.13.35")
            if not member.isfile() or member.size > 32 * 1024**2:
                raise ValueError("Unexpected FMOD SDK ARM64 library")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("FMOD SDK library is unreadable")
            destination = target / f"lib{name}.so.13.35"
            with stream, destination.open("wb") as output:
                shutil.copyfileobj(stream, output)
            if read_elf_architecture(destination) != "aarch64":
                raise ValueError("FMOD SDK library is not Linux AArch64")
            for alias in (f"lib{name}.so", f"lib{name}.so.13"):
                shutil.copyfile(destination, target / alias)
        license = archive.getmember("fmodstudioapi20235linux/doc/LICENSE.TXT")
        if not license.isfile() or license.size > 1024**2:
            raise ValueError("Unexpected FMOD SDK license file")
        stream = archive.extractfile(license)
        if stream is None:
            raise ValueError("FMOD SDK license is unreadable")
        notice = game.parent / "licenses/LICENSE-FMOD-SDK.txt"
        notice.parent.mkdir(parents=True, exist_ok=True)
        with stream, notice.open("wb") as output:
            shutil.copyfileobj(stream, output)


def build_game(*, source_path, output_path, inspection, runtime, fmod_sdk,
               force, archive_type, progress, stage_progress, download_progress):
    """Run through the ordinary Godot backend, router and shared ZIP installer."""
    from rpgmframe.godot import find_godot_pack
    from rpgmframe.godot_backend import GodotBuildError, _staging_path, _install
    from rpgmframe.godot_extension_runtime import resolve_runtime, install_runtime
    from rpgmframe.launchers import godot_launcher_body
    from rpgmframe.models import BuildResult, EngineVariant
    from megcfbt.frame_package import write_frame_metadata
    from renframe.source_safety import validate_copy_tree

    staging = _staging_path(output_path)
    def stage(value, text):
        if stage_progress:
            stage_progress(value, text)
        if progress:
            progress(text)
    try:
        validate_copy_tree(inspection.game_root)
        pack = find_godot_pack(inspection.game_root)
        stage(.07, "Verifying audited Until Then source pack (3.25 GiB)")
        identity = validate_source(pack, inspection.game_root, lambda done, total:
            stage_progress(.07 + .12 * done / max(total, 1), "Verifying Until Then source SHA-256") if stage_progress else None)
        sdk = validate_fmod_sdk(fmod_sdk) if fmod_sdk else find_fmod_sdk()
        if sdk is None:
            raise ValueError("Select the owner-supplied FMOD Studio API 2.02.35 Linux SDK with --fmod-sdk or the GUI FMOD button.")
        stage(.21, "Resolving audited Until Then ARM64 runtime and extensions")
        selected = resolve_runtime(runtime, progress=progress, download_progress=download_progress)
        if selected == output_path or selected in output_path.parents or output_path in selected.parents:
            raise ValueError("Output must not overlap the selected runtime")
        if output_path.exists() and not force:
            raise ValueError(f"Output already exists: {output_path}. Pass --force to replace it.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
        stage(.4, "Copying Until Then content; original installation remains untouched")
        game = staging / "game"
        def ignore(folder, contents):
            return [name for name in contents if name.lower().endswith((".exe", ".dll", ".pdb", ".pyc"))
                    or name in {".git", "__pycache__", ".megcfbt", "override.cfg", "steam_appid.txt"}]
        def copy_content(source, target):
            if Path(source) != pack.path:
                return shutil.copy2(source, target)
            hashed = hashlib.sha256()
            count = 0
            with Path(source).open("rb") as original, Path(target).open("wb") as converted:
                while chunk := original.read(8 * 1024**2):
                    converted.write(chunk)
                    hashed.update(chunk)
                    count += len(chunk)
                    if stage_progress:
                        stage_progress(.4 + .24 * count / max(PACK_SIZE, 1), "Copying and verifying Until Then content")
            if hashed.hexdigest() != PACK_SHA256:
                raise ValueError("Until Then changed while copying; retry after Steam finishes updating")
            shutil.copystat(source, target)
            return str(target)
        shutil.copytree(inspection.game_root, game, ignore=ignore, symlinks=False, copy_function=copy_content)
        original_override = inspection.game_root / "override.cfg"
        if original_override.is_file():
            shutil.copy2(original_override, staging / "source-override.cfg")
        stage(.66, "Installing native extensions and owner-supplied FMOD audio libraries")
        install_runtime(selected, staging)
        install_owner_fmod(sdk, game)
        overlays = install_overlay(game / pack.path.name, game)
        # A stable isolated save namespace protects original-install saves and
        # keeps converted saves usable across package updates and new ZIPs.
        (game / "override.cfg").write_text('[application]\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="megcfbt/until-then"\n', encoding="utf-8", newline="\n")
        for folder in (staging, game):
            (folder / "steam_appid.txt").write_bytes((str(APPID) + "\n").encode("ascii"))
        launcher = staging / "launch.sh"
        launcher.write_text(godot_launcher_body("game/" + pack.path.name,
            resource_overlay="game/untilthen-native-overlay.pck",
            library_directories=("game/addons/fmod/native/linux", "game/addons/godotsteam/linux"),
            preserve_launch_environment=True, require_native_steam=True,
            steam_app_id=APPID), encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
        (staging / "godot-compatibility.json").write_text(json.dumps({
            "profile_id": PROFILE, "status": "experimental-opening-gameplay-verified",
            "source_pack_sha256": PACK_SHA256, "source_buildid": "23785927",
            "overlay_files": overlays, "fmod_sdk_sha256": FMOD_SHA256,
            "save_directory": "megcfbt/until-then", "achievements": "unverified",
            "playtime": "unverified", "library_linking": "unsupported", "deduplication": "unsupported",
        }, indent=2) + "\n", encoding="utf-8")
        write_frame_metadata(staging, name="Until Then", launcher_path=launcher,
            engine="godot", backend="rpgmframe", engine_version="4.1.4",
            runtime_engine_version="4.1.4", compatibility_profile=PROFILE,
            steam_identity=identity, steam_runtime_appid=APPID)
        _install(staging, output_path, force=force)
        stage(1, "Experimental Until Then ARM64 package complete")
    except Exception as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise GodotBuildError(f"Until Then conversion failed: {error}") from error
    warnings = list(inspection.warnings) + ["Until Then: opening gameplay, audio, controller, save/reload and normal exit verified on Frame; full-game coverage and achievements remain unverified. Original-entry linking and asset deduplication are deferred."]
    return BuildResult(success=True, source_path=source_path, output_path=output_path,
        launcher_path=output_path / "launch.sh", runtime_path=selected,
        engine=EngineVariant.GODOT, engine_version="4.1.4", game_name="Until Then",
        runtime_architecture="aarch64", warnings=warnings)
