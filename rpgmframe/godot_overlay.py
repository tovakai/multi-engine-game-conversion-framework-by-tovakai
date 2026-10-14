"""Small, bounded Godot 4.1 resource overlays; never rewrite the source pack."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path, PurePosixPath


def resource_path(name: str) -> str:
    if (not isinstance(name, str) or not name or any(char in name for char in '\\:"<>|?*$`')
            or any(ord(char) < 32 for char in name) or PurePosixPath(name).is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError("Unsafe Godot overlay resource path")
    return name


def write_pack(destination: Path, files: dict[str, bytes]) -> None:
    entries = []
    directory_size = 100
    for name, data in sorted(files.items()):
        resource_path(name)
        if not isinstance(data, bytes) or len(data) > 16 * 1024**2:
            raise ValueError("Unexpected overlay resource size/type")
        encoded = ("res://" + name).encode("utf-8")
        encoded += bytes((-len(encoded)) % 4)
        directory_size += 4 + len(encoded) + 36
        entries.append((encoded, data))
    offset = (directory_size + 15) // 16 * 16
    directory = bytearray(struct.pack("<6IQ", 0x43504447, 2, 4, 1, 4, 0, 0)
                          + bytes(64) + struct.pack("<I", len(entries)))
    blocks = []
    for encoded, data in entries:
        directory += (struct.pack("<I", len(encoded)) + encoded
                      + struct.pack("<QQ", offset, len(data))
                      + hashlib.md5(data).digest() + struct.pack("<I", 0))
        padding = (-len(data)) % 16
        blocks.append(data + bytes(padding))
        offset += len(data) + padding
    if destination.is_symlink():
        raise ValueError("Overlay destination is a symlink")
    with destination.open("wb") as stream:
        stream.write(directory)
        stream.write(bytes((-len(directory)) % 16))
        for block in blocks:
            stream.write(block)


def read_resource(pack: Path, name: str, *, limit: int = 1024**2) -> bytes:
    """Read one unencrypted v2 resource, checking bounds, duplicates and checksum."""
    resource_path(name)
    selected = None
    size = pack.stat().st_size
    with pack.open("rb") as stream:
        def read(count):
            data = stream.read(count)
            if len(data) != count:
                raise ValueError("Truncated Godot pack")
            return data

        header = read(96)
        if struct.unpack("<6I", header[:24]) != (0x43504447, 2, 4, 1, 4, 0):
            raise ValueError("Unexpected Godot pack layout")
        base = struct.unpack_from("<Q", header, 24)[0]
        count = struct.unpack("<I", read(4))[0]
        if count > 1_000_000:
            raise ValueError("Unbounded Godot pack directory")
        for _ in range(count):
            length = struct.unpack("<I", read(4))[0]
            if not 0 < length <= 65536:
                raise ValueError("Unsafe Godot pack path length")
            path = read(length).rstrip(b"\0").decode("utf-8")
            offset, length = struct.unpack("<QQ", read(16))
            checksum = read(16)
            flags = struct.unpack("<I", read(4))[0]
            if path == "res://" + name:
                if selected is not None:
                    raise ValueError("Duplicate requested Godot resource")
                if flags or length > limit or base + offset + length > size:
                    raise ValueError("Unsafe Godot resource layout")
                selected = (base + offset, length, checksum)
            # The directory itself cannot extend past the source pack.
            if stream.tell() > size:
                raise ValueError("Invalid Godot pack directory")
        if selected is None or selected[0] < stream.tell():
            raise ValueError("Requested Godot resource missing or overlaps directory")
        stream.seek(selected[0])
        data = read(selected[1])
        if hashlib.md5(data).digest() != selected[2]:
            raise ValueError("Godot resource checksum mismatch")
        return data


def extension(entry: str, library: str, dependencies=()) -> bytes:
    resource_path(library)
    text = (f'[configuration]\nentry_symbol="{entry}"\ncompatibility_minimum=4.1\n'
            f'[libraries]\nlinux.release="res://{library}"\nlinux.debug="res://{library}"\n')
    if dependencies:
        text += "[dependencies]\nlinux={" + ", ".join(
            '"res://' + resource_path(path) + '":""' for path in dependencies) + "}\n"
    return text.encode("utf-8")
