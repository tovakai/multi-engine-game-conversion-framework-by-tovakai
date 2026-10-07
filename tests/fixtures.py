"""Shared fake Ren'Py game / runtime fixtures for tests (no copyrighted content)."""

from __future__ import annotations

import struct
from pathlib import Path

# ELF e_machine
EM_X86_64 = 62
EM_AARCH64 = 183


def write_elf(path: Path, machine: int) -> None:
    """Write a minimal ELF header with the given e_machine value."""
    data = bytearray(64)
    data[0:4] = b"\x7fELF"
    data[4] = 2  # 64-bit
    data[5] = 1  # little endian
    data[6] = 1
    struct.pack_into("<H", data, 16, 3)  # ET_DYN
    struct.pack_into("<H", data, 18, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))


def make_game(
    root: Path,
    *,
    version: str = "8.3.2",
    lib_arch: str = "py3-linux-x86_64",
    name: str = "Example Game",
    with_native_x86: bool = False,
    script_extra: str | None = None,
) -> Path:
    """Create a minimal fake distributed Ren'Py game (x86 desktop style)."""
    root.mkdir(parents=True, exist_ok=True)
    game = root / "game"
    renpy = root / "renpy"
    game.mkdir(parents=True, exist_ok=True)
    renpy.mkdir(parents=True, exist_ok=True)

    script = "label start:\n    return\n"
    if script_extra:
        script += script_extra
    (game / "script.rpy").write_text(script, encoding="utf-8")
    (game / "archive.rpa").write_bytes(b"RPA-3.0\x00fake")
    (game / "images").mkdir(exist_ok=True)
    (game / "images" / "bg.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (game / "audio").mkdir(exist_ok=True)
    (game / "audio" / "beep.ogg").write_bytes(b"OggSfake")

    (renpy / "__init__.py").write_text("# renpy\n", encoding="utf-8")
    (renpy / "versions.py").write_text(
        f'version = "{version}"\nvc_version = 1\n',
        encoding="utf-8",
    )
    (root / "renpy.py").write_text("# renpy entry\n", encoding="utf-8")
    (root / "lib" / lib_arch).mkdir(parents=True, exist_ok=True)
    write_elf(root / "lib" / lib_arch / "librenpy.so", EM_X86_64)
    (root / f"{name}.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    if with_native_x86:
        write_elf(game / "python-packages" / "mod.so", EM_X86_64)

    return root


def make_runtime(
    root: Path,
    *,
    version: str = "8.3.4",
    arch: str = "aarch64",
    with_template_game: bool = True,
    with_renpy_sh: bool = True,
) -> Path:
    """
    Create a minimal fake Ren'Py SDK/runtime.

    ``arch`` is ``aarch64`` or ``x86_64``.
    """
    root.mkdir(parents=True, exist_ok=True)
    renpy = root / "renpy"
    renpy.mkdir(parents=True, exist_ok=True)
    (renpy / "__init__.py").write_text("# renpy runtime\n", encoding="utf-8")
    (renpy / "versions.py").write_text(
        f'version = "{version}"\nvc_version = 1\n',
        encoding="utf-8",
    )
    (root / "renpy.py").write_text(
        "#!/usr/bin/env python3\n# renpy.py stub\n",
        encoding="utf-8",
    )

    if arch == "aarch64":
        lib_name = "py3-linux-aarch64"
        machine = EM_AARCH64
    elif arch == "x86_64":
        lib_name = "py3-linux-x86_64"
        machine = EM_X86_64
    else:
        raise ValueError(f"unsupported arch fixture: {arch}")

    lib_dir = root / "lib" / lib_name
    lib_dir.mkdir(parents=True, exist_ok=True)
    write_elf(lib_dir / "python", machine)
    write_elf(lib_dir / "librenpy.so", machine)

    if with_renpy_sh:
        (root / "renpy.sh").write_text(
            "#!/bin/sh\n"
            'ROOT="$(dirname "$0")"\n'
            'exec "$ROOT/lib/' + lib_name + '/python" "$ROOT/renpy.py" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )

    if with_template_game:
        (root / "game").mkdir(parents=True, exist_ok=True)
        (root / "game" / "script.rpy").write_text(
            "# template game — should be replaced\nlabel start:\n    return\n",
            encoding="utf-8",
        )

    # SDK junk that should be ignored when present
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__" / "x.pyc").write_bytes(b"junk")

    return root
