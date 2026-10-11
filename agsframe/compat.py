"""Identified Windows graphics hooks with native AGS replacements."""
from pathlib import Path
import hashlib
import re

# This D3D9 rendering hook has no required script API in the tested export.
# Identify the implementation, rather than assuming every similarly named
# DLL is safe to omit. The replacement is AGS's native OpenGL vsync setting.
D3D_VSYNC_SHA256 = '424981fbad2cd3d84c48d734241bdf8f5b0816ac34ba3c35c0dbb6347d585917'


def is_windows_vsync_hook(path: Path) -> bool:
    return (path.name.casefold() == 'agsd3dvsync.dll' and path.stat().st_size < 1024*1024
            and hashlib.sha256(path.read_bytes()).hexdigest() == D3D_VSYNC_SHA256)


def native_graphics_config(destination: Path, *, replace_vsync_hook: bool) -> None:
    config = destination/'acsetup.cfg'
    if not config.exists():
        return
    text = config.read_text(encoding='utf-8-sig')
    # Preserve the rest of the game's setup, including translations and scaling.
    text = re.sub(r'(?im)^(\s*(?:gfxdriver|driver)\s*=\s*)(?:D3D9|D3D|Direct3D)\s*$',r'\1OGL',text)
    if replace_vsync_hook:
        text = re.sub(r'(?im)^(\s*vsync\s*=\s*)[01]\s*$',r'\g<1>1',text)
    config.write_text(text,encoding='utf-8',newline='\n')
