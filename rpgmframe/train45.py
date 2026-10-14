"""Hash-gated Train45 Godot 4.5 / GodotSteam 4.19.1 conversion."""
from pathlib import Path
import hashlib
import json
import shutil

APPID = 3711590
PROFILE = "experimental-train45-build25227748-native-v1"
RUNTIME_KIND = "godot-train45"
RECIPE = "godot-4.5-train45-native-arm64-v1"
PACK_SIZE = 1552603220
PACK_SHA256 = "8359ff2daae6d8311602a9181c771695d106d7fed7433b2a6e5611c2a7228132"
SOURCE_LIBRARIES = {
    "libgodotsteam.windows.template_release.x86_64.dll": "20defe9aeffd888a639f8afef5544cc9cff46b2074459a47207927d1f783ce47",
    "steam_api64.dll": "eb17909a76668cf9ae0b92a618a34a50f6c73d3a6787cb4dd8ce36a8b10bfb75",
}


def candidate(pack, root):
    from rpgmframe.until_then import digest
    if pack is None or pack.version != "4.5.0" or pack.pack_format != 3 or pack.size != PACK_SIZE or pack.path.is_symlink():
        return False
    try:
        return all((root / name).is_file() and not (root / name).is_symlink()
            and (root / name).stat().st_size < 64 * 1024**2
            and digest(root / name) == expected for name, expected in SOURCE_LIBRARIES.items())
    except OSError:
        return False


def build_game(*, source_path, output_path, inspection, runtime, force,
               archive_type, progress, stage_progress, download_progress):
    from renframe.source_safety import validate_copy_tree
    from rpgmframe.godot import find_godot_pack, materialize_pack
    from rpgmframe.godot_backend import GodotBuildError, _staging_path, _install
    from rpgmframe.godot_extension_runtime import resolve_runtime, install_runtime
    from rpgmframe.until_then import digest
    from rpgmframe.launchers import godot_launcher_body
    from rpgmframe.models import BuildResult, EngineVariant
    from megcfbt.steam_context import verified_source_identity
    from megcfbt.frame_package import write_frame_metadata

    staging = _staging_path(output_path)
    def stage(value, message):
        if progress: progress(message)
        if stage_progress: stage_progress(value, message)
    try:
        validate_copy_tree(inspection.game_root)
        pack = find_godot_pack(inspection.game_root)
        if not candidate(pack, inspection.game_root):
            raise ValueError("Train45 source is not the audited build 25227748")
        identity = verified_source_identity(inspection.game_root, APPID)
        stage(.1, "Resolving verified Train45 ARM64 release runtime and GodotSteam extension")
        selected = resolve_runtime(runtime, recipe=RECIPE, progress=progress, download_progress=download_progress)
        if selected == output_path or selected in output_path.parents or output_path in selected.parents:
            raise ValueError("Output must not overlap the selected runtime")
        if output_path.exists() and not force:
            raise ValueError("Output already exists; pass --force to replace it")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
        game = staging / "game"
        shutil.copytree(inspection.game_root, game, ignore=lambda folder, names: [n for n in names
            if n.lower().endswith((".exe", ".dll", ".pdb", ".pyc")) or n in {".megcfbt", ".git", "override.cfg", "steam_appid.txt"}
            or Path(folder) / n == pack.path])
        stage(.35, "Extracting and verifying Train45 embedded game pack; original files remain untouched")
        materialize_pack(pack, game / "Train45.pck")
        if digest(game / "Train45.pck", lambda done, total: stage_progress(.35 + .3 * done / max(total, 1), "Verifying Train45 SHA-256") if stage_progress else None) != PACK_SHA256:
            raise ValueError("Train45 pack does not match audited build 25227748; a source update requires a new profile")
        install_runtime(selected, staging, recipe=RECIPE)
        original_override = inspection.game_root / "override.cfg"
        if original_override.is_file(): shutil.copy2(original_override, staging / "source-override.cfg")
        (game / "override.cfg").write_text('[application]\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="megcfbt/train45"\n', encoding="utf-8", newline="\n")
        for folder in (staging, game): (folder / "steam_appid.txt").write_bytes(b"3711590\n")
        launcher = staging / "launch.sh"
        text = godot_launcher_body("game/Train45.pck", library_directories=("game/addons/godotsteam/linuxarm64",),
            preserve_launch_environment=True, require_native_steam=True, steam_app_id=APPID)
        # Godot's dependency descriptor resolves this path inside the converted
        # game. Use the installed native API without distributing Valve binaries.
        bootstrap = '''for directory in "$ROOT/game" "$ROOT/game/addons" "$ROOT/game/addons/godotsteam" "$ROOT/game/addons/godotsteam/linuxarm64"; do
    if [[ ! -d "$directory" || -L "$directory" ]]; then
        echo "ERROR: Unsafe Steam API directory. Re-extract the converted package." >&2
        exit 1
    fi
done
api="$ROOT/game/addons/godotsteam/linuxarm64/libsteam_api.so"
if [[ -e "$api" || -L "$api" ]]; then
    if [[ ! -L "$api" || "$(readlink "$api")" != "$steam_arm64_dir/libsteam_api.so" ]]; then
        echo "ERROR: Unexpected native Steam API path. Re-extract the converted package to repair it." >&2
        exit 1
    fi
else
    ln -s "$steam_arm64_dir/libsteam_api.so" "$api"
fi
'''
        text = text.replace('cd "$ROOT/game"', bootstrap + '\ncd "$ROOT/game"')
        launcher.write_text(text, encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
        (staging / "godot-compatibility.json").write_text(json.dumps({"profile_id": PROFILE,
            "source_pack_sha256": PACK_SHA256, "source_buildid": "25227748", "save_directory": "megcfbt/train45",
            "status": "experimental-gameplay-tested", "achievements": "unverified", "playtime": "unverified",
            "library_linking": "unsupported", "deduplication": "unsupported"}, indent=2) + "\n", encoding="utf-8")
        write_frame_metadata(staging, name="Train45", launcher_path=launcher, engine="godot", backend="rpgmframe",
            engine_version="4.5.0", runtime_engine_version="4.5.0", compatibility_profile=PROFILE,
            steam_identity=identity, steam_runtime_appid=APPID)
        _install(staging, output_path, force=force)
        stage(1, "Experimental Train45 ARM64 conversion complete")
    except Exception as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise GodotBuildError(f"Train45 conversion failed: {error}") from error
    return BuildResult(success=True, source_path=source_path, output_path=output_path,
        launcher_path=output_path / "launch.sh", runtime_path=selected, engine=EngineVariant.GODOT,
        engine_version="4.5.0", game_name="Train45", runtime_architecture="aarch64",
        warnings=list(inspection.warnings) + ["Train45 research gameplay passed on Frame; full-game, achievements and playtime remain unverified. Linking/deduplication unsupported."])
