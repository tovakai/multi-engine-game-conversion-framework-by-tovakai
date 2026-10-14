"""Verified native-extension bundles shared by audited Godot profiles."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from megcfbt.native_runtime import _cache_parent
from megcfbt.runtime_download import ensure_bundle
from renframe.source_safety import validate_copy_tree
from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot_overlay import resource_path
from rpgmframe.until_then import RECIPE, LIBRARIES, digest, extension_directory

INDEX_PATH = Path(__file__).with_name("godot_extension_runtime_index.json")
EMBEDDED_PATH = Path(__file__).with_name("runtime_support")
REQUIRED = {"godot.arm64", *(f"extensions/{name}/{library}" for name, (_, library) in LIBRARIES.items())}


def recipe_entry():
    try:
        entry = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["recipes"][RECIPE]
        if (entry.get("recipe_id") != RECIPE or entry.get("executable") != "godot.arm64"
                or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))
                or not entry.get("url", "").startswith("https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/")
                or not re.fullmatch(r"[a-z0-9.-]+\.tar\.gz", entry.get("archive_name", ""))):
            raise ValueError("Invalid Godot extension runtime index")
        names = entry["archive_files"]
        if not isinstance(names, list) or len(names) != len(set(names)) or not (REQUIRED | {"runtime.json"}) <= set(names):
            raise ValueError("Incomplete Godot extension runtime index")
        for name in names:
            resource_path(name)
        hashes = entry["files"]
        if (not isinstance(hashes, dict) or set(hashes) != set(names) - {"runtime.json"}
                or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())):
            raise ValueError("Missing pinned Godot extension file hashes")
        return entry
    except (OSError, KeyError, TypeError, ValueError):
        return None


def validate_runtime(root: Path, entry=None):
    entry = recipe_entry() if entry is None else entry
    if entry is None or not root.is_dir() or root.is_symlink():
        raise ValueError("Audited Until Then runtime bundle is unavailable")
    validate_copy_tree(root)
    manifest = root / "runtime.json"
    if manifest.is_symlink() or manifest.stat().st_size > 1024**2:
        raise ValueError("Unsafe Godot runtime manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("recipe_id") != RECIPE or data.get("architecture") != "aarch64"
            or data.get("engine_version") != "4.1.4"
            or data.get("capabilities") != {"resource_overlay_before_extensions": True,
                "extension_symbols": "isolated", "fmod_abi": "2.02", "steam_api_provider": "steam-frame-installed"}
            or data.get("files") != entry["files"]):
        raise ValueError("Wrong Godot extension runtime recipe or capabilities")
    for name, expected in entry["files"].items():
        file = root / resource_path(name)
        if (not file.is_file() or file.is_symlink() or file.resolve() != file
                or digest(file) != expected):
            raise ValueError(f"Godot extension runtime integrity failure: {name}")
        if name in REQUIRED and read_elf_architecture(file) != "aarch64":
            raise ValueError(f"Godot extension runtime is not Linux AArch64: {name}")
    return data


def resolve_runtime(selected=None, *, progress=None, download_progress=None):
    if selected:
        root = Path(selected).expanduser().resolve()
        validate_runtime(root)
        return root
    entry = recipe_entry()
    if entry is None:
        raise ValueError("No audited Until Then ARM64 runtime is indexed")
    def valid(path):
        try:
            validate_runtime(path, entry)
            return True
        except (OSError, KeyError, TypeError, ValueError):
            return False
    embedded = EMBEDDED_PATH / entry["archive_name"]
    return ensure_bundle(entry, _cache_parent() / "godot-extensions" / RECIPE,
        validate=valid, progress=progress, download_progress=download_progress,
        archive_path=embedded if embedded.is_file() else None)


def install_runtime(source: Path, package: Path):
    entry = recipe_entry()
    validate_runtime(source, entry)
    for name in entry["archive_files"]:
        if name.startswith("extensions/"):
            _, component, library = name.split("/")
            target = package / "game" / extension_directory(component) / library
        else:
            target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    (package / "godot.arm64").chmod(0o755)
