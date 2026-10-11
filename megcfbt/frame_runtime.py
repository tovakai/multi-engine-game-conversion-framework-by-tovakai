"""Install the shipped, source-backed Frame Steam graphics routing helper."""
from pathlib import Path
import hashlib
import json
import shutil
from renframe.elf import read_elf_architecture


def install_steam_graphics_guard(destination: Path) -> None:
    assets = Path(__file__).resolve().parent/'runtime_support'
    binary = assets/'libframe_steam_env.so'
    manifest = assets/'frame_steam_env.json'
    try:
        receipt = json.loads(manifest.read_text(encoding='utf-8'))
        if (read_elf_architecture(binary) != 'aarch64'
                or hashlib.sha256(binary.read_bytes()).hexdigest() != receipt['sha256']):
            raise ValueError('Frame graphics helper failed integrity/architecture validation.')
        shutil.copy2(binary,destination/binary.name)
        shutil.copy2(manifest,destination/manifest.name)
        shutil.copy2(assets/'frame_steam_env.c',destination/'frame_steam_env.c')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise ValueError(f'Could not install Frame Steam graphics helper: {exc}') from exc
