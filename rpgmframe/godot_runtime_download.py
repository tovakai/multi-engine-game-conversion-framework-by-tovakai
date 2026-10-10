"""Verified, cached GitHub Release runtime downloads.

Only recipes explicitly listed in the shipped runtime index are eligible.
Never download an arbitrary executable based on a game's untrusted metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot_custom_runtime import RECIPE_ID, GODOTSTEAM_351_RECIPE, GODOTSTEAM_460_RECIPE, GODOTSTEAM_472_RECIPE

INDEX_PATH = Path(__file__).resolve().parent / "godot_runtime_index.json"
RUNTIME_SUPPORT_FILES = (
    'AUTHORS-Godot.md', 'COPYRIGHT-Godot.txt', 'LICENSE-Converter.txt',
    'LICENSE-Godot.txt', 'LICENSE-GodotSteam.txt', 'NOTICE.txt',
    'SOURCE-BUILD.txt', 'THIRD_PARTY_NOTICES.md', 'godotsteam-legacy-cpp.patch',
    'godotsteam-legacy-header.patch', 'runtime-source-build.sh', 'variant-release-guard.patch',
)
BUILTIN_RECIPES = {
    RECIPE_ID: {
        "url": (
            "https://github.com/tovakai/"
            "multi-engine-game-conversion-framework-by-tovakai/releases/download/"
            "runtime-godot-3.7-dev1-godotsteam-3.30-arm64-v1/"
            "godot-3.7-dev1-godotsteam-3.30-frame-arm64-v1.tar.gz"
        ),
        "sha256": "f87130aa44fae591a098eb03df8a419f84b47d25100756f04bb645e44102e34a",
        "status": "validated",
    }
}
DownloadProgress = Callable[[int, int | None], None]
UPSTREAM_RECIPES = {
    GODOTSTEAM_460_RECIPE: {
        'url': 'https://codeberg.org/godotsteam/godotsteam/releases/download/v4.17.1/godotsteam-g46-s163-gs4171-templates.tar.xz',
        'sha256': 'f54f7b065014ae0d69c4ae5ae097eb50b2210e7eaae723fe09f23516f6f62ada',
        'binary': 'templates/linuxarm64/godotsteam.46.template.arm64', 'engine_version': '4.6.0',
        'godotsteam_version': '4.17.1',
        'steam_library': 'templates/linuxarm64/libsteam_api.so', 'multi_platform_archive': True,
        'pack_loading': 'adjacent',
    },
    GODOTSTEAM_472_RECIPE: {
        'url': 'https://codeberg.org/godotsteam/godotsteam/releases/download/v4.23/godotsteam-g472-s165-gs423-templates.tar.xz',
        'sha256': '8f1891f3cc6b9f3f3d535be12d2bcc5c1496f876f8873d3f42ce028ce2035339',
        'binary': 'linuxarm64/godotsteam.472.template.arm64', 'engine_version': '4.7.2',
        'godotsteam_version': '4.23',
        'steam_library': 'linuxarm64/libsteam_api.so', 'multi_platform_archive': True,
        'pack_loading': 'adjacent',
    },
}


class RuntimeDownloadError(RuntimeError):
    pass


def recipe_entry(recipe_id: str) -> dict | None:
    if recipe_id in UPSTREAM_RECIPES:
        return dict(UPSTREAM_RECIPES[recipe_id])
    if recipe_id not in {RECIPE_ID, GODOTSTEAM_351_RECIPE}:
        return None
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        index = {"recipes": BUILTIN_RECIPES}
    try:
        entry = index["recipes"][recipe_id]
    except (KeyError, TypeError):
        return None
    if not isinstance(entry, dict):
        return None
    url, digest = entry.get("url"), entry.get("sha256")
    if not isinstance(url, str) or not url.startswith(
        "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/"
    ):
        return None
    if not isinstance(digest, str) or len(digest) != 64:
        return None
    try:
        int(digest, 16)
    except ValueError:
        return None
    files = entry.get('archive_files', ['godot.arm64','runtime.json'])
    if (not isinstance(files, list) or not all(isinstance(name,str) for name in files)
            or len(files) != len(set(files))
            or not {'godot.arm64','runtime.json'}.issubset(files)
            or not set(files).issubset({'godot.arm64','runtime.json',*RUNTIME_SUPPORT_FILES})):
        return None
    return entry


def downloadable(recipe_id: str) -> bool:
    return recipe_entry(recipe_id) is not None


def _validate(path: Path, recipe_id: str) -> bool:
    binary = path / "godot.arm64"
    manifest = path / "runtime.json"
    if not binary.is_file() or not manifest.is_file():
        return False
    if read_elf_architecture(binary) != "aarch64":
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    entry = recipe_entry(recipe_id)
    if recipe_id == GODOTSTEAM_351_RECIPE:
        capabilities = data.get('capabilities')
        dependency = data.get('steam_api_dependency')
        if (entry is None or data.get('engine_version') != '3.5.1'
                or not isinstance(capabilities, dict)
                or capabilities.get('legacy_steam_init_dictionary') is not True
                or not isinstance(dependency, dict)
                or dependency.get('provider') != 'steam-frame-installed'):
            return False
        hashes = data.get('files')
        if not isinstance(hashes, dict):
            return False
        for name in entry.get('archive_files', ['godot.arm64','runtime.json']):
            if name == 'runtime.json':
                continue
            file = path/name
            if not file.is_file() or hashes.get(name) != hashlib.sha256(file.read_bytes()).hexdigest():
                return False
    if recipe_id in UPSTREAM_RECIPES:
        steam = path / 'libsteam_api.so'
        if read_elf_architecture(steam) != 'aarch64':
            return False
        hashes = data.get('files', {})
        if not isinstance(hashes, dict):
            return False
        for name in ('godot.arm64','libsteam_api.so'):
            if hashes.get(name) != hashlib.sha256((path/name).read_bytes()).hexdigest():
                return False
    return (
        isinstance(data, dict)
        and (data.get("recipe_id") == recipe_id
             or (recipe_id == RECIPE_ID and data.get("recipe") == "godot-3.7-dev1-godotsteam-3.30-arm64"))
    )


def _cache_root() -> Path:
    configured = os.environ.get("RPGMFRAME_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "tovakai" / "cache"
    return Path.home() / ".cache" / "tovakai"


def _extract_archive(archive: Path, extracted: Path, entry: dict, *, upstream: bool) -> dict:
    mapping = ({entry['binary']: 'godot.arm64', entry.get('steam_library','libsteam_api.so'): 'libsteam_api.so'}
               if upstream else {name:name for name in entry.get('archive_files', ['godot.arm64','runtime.json'])})
    seen = set()
    try:
        with tarfile.open(archive, 'r:*') as tar:
            for member in tar:
                if upstream and entry.get('multi_platform_archive') and member.name not in mapping:
                    continue
                if not member.isfile() or member.name not in mapping or member.name in seen:
                    raise RuntimeDownloadError(f'Unsafe or unexpected runtime archive member: {member.name}')
                if member.size > 512 * 1024**2:
                    raise RuntimeDownloadError('Runtime archive member exceeds 512 MiB limit')
                seen.add(member.name)
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeDownloadError('Unreadable runtime archive member')
                with source, (extracted / mapping[member.name]).open('wb') as dest:
                    shutil.copyfileobj(source, dest)
            if seen != set(mapping):
                raise RuntimeDownloadError('Runtime archive is missing required files')
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise RuntimeDownloadError(f'Could not unpack verified runtime archive: {exc}') from exc
    return mapping


def ensure_downloaded_runtime(
    recipe_id: str,
    *,
    progress: Callable[[str], None] | None = None,
    download_progress: DownloadProgress | None = None,
) -> Path:
    entry = recipe_entry(recipe_id)
    if entry is None:
        raise RuntimeDownloadError(f"No published runtime for recipe {recipe_id}")

    target = _cache_root() / "runtimes" / "godot-custom" / recipe_id
    if _validate(target, recipe_id):
        if progress:
            progress("Using cached custom GodotSteam ARM64 runtime")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".godotsteam-", dir=target.parent) as temp:
        tmp = Path(temp)
        archive = tmp / "runtime.tar.gz"
        digest = hashlib.sha256()
        count = 0
        if progress:
            progress("Downloading custom GodotSteam ARM64 runtime…")
        try:
            with urllib.request.urlopen(entry["url"], timeout=45) as response:
                length_header = response.headers.get("Content-Length")
                total = int(length_header) if length_header and length_header.isdigit() else None
                with archive.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > 2 * 1024**3:
                            raise RuntimeDownloadError("Runtime download exceeds 2 GiB limit")
                        digest.update(chunk)
                        output.write(chunk)
                        if download_progress:
                            download_progress(count, total)
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeDownloadError(f"Could not download custom runtime: {exc}") from exc

        if progress:
            progress("Verifying downloaded runtime SHA-256…")
        if digest.hexdigest().lower() != entry["sha256"].lower():
            raise RuntimeDownloadError("Runtime download SHA-256 mismatch; refusing to use it")

        extracted = tmp / "extracted"
        extracted.mkdir()
        upstream = recipe_id in UPSTREAM_RECIPES
        mapping = _extract_archive(archive, extracted, entry, upstream=upstream)
        if upstream:
            receipt = {'kind':'godot-custom','recipe_id':recipe_id,'architecture':'aarch64',
                       'engine_version':entry['engine_version'],'godotsteam_version':entry['godotsteam_version'],
                       'source_url':entry['url'],'archive_sha256':entry['sha256'],
                       'pack_loading':entry.get('pack_loading','main-pack'),
                       'files':{name:hashlib.sha256((extracted/name).read_bytes()).hexdigest() for name in mapping.values()}}
            (extracted/'runtime.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        if not _validate(extracted, recipe_id):
            raise RuntimeDownloadError("Downloaded runtime failed ARM64/recipe validation")
        (extracted / "godot.arm64").chmod(0o755)
        # Both paths are siblings on the same filesystem. Publish the complete
        # verified tree by rename and retain the previous cache on failure.
        backup = tmp / 'previous-cache'
        try:
            if target.exists():
                target.rename(backup)
            extracted.rename(target)
        except OSError as exc:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise RuntimeDownloadError(f'Could not install verified runtime cache: {exc}') from exc
    if progress:
        progress("Custom GodotSteam runtime cached. Continuing conversion…")
    return target
