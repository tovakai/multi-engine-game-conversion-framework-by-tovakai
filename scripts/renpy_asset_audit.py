"""Read-only RPA-3/loose asset inventory; never executes archive pickle globals.

Run with Python 3: python scripts/renpy_asset_audit.py /path/to/package
Output contains filenames and image metadata, never asset/script contents.
"""
import argparse
import collections
import io
import json
import pickle
import struct
import time
import zlib
from pathlib import Path


class IndexUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError("Archive index contains executable pickle globals")


def png_dimensions(header):
    if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) >= 24:
        return struct.unpack(">II", header[16:24])
    return None


def audit(root):
    rows = []
    archives = []
    game = root / "game"
    for path in sorted(game.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(game).as_posix()
        if path.suffix.lower() != ".rpa":
            with path.open("rb") as stream:
                dimensions = png_dimensions(stream.read(32))
            rows.append(dict(name=name, source="loose", bytes=path.stat().st_size,
                             dimensions=dimensions))
            continue
        with path.open("rb") as stream:
            header = stream.read(40)
            if not header.startswith(b"RPA-3.0 "):
                archives.append(dict(name=name, unsupported_header=True))
                continue
            offset = int(header[8:24], 16)
            key = int(header[25:33], 16)
            stream.seek(offset)
            started = time.perf_counter()
            compressed = stream.read()
            read_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            decoded = zlib.decompress(compressed)
            inflate_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            index = IndexUnpickler(io.BytesIO(decoded), encoding="bytes").load()
            parse_ms = (time.perf_counter() - started) * 1000
            archives.append(dict(name=name, bytes=path.stat().st_size,
                                 index_bytes=len(compressed), entries=len(index),
                                 index_read_ms=read_ms, index_inflate_ms=inflate_ms,
                                 index_parse_ms=parse_ms))
            for member, chunks in index.items():
                if isinstance(member, bytes):
                    member = member.decode("utf-8", "replace")
                size = sum(chunk[1] ^ key for chunk in chunks)
                chunk = chunks[0]
                prefix = chunk[2] if len(chunk) > 2 else b""
                if isinstance(prefix, str):
                    prefix = prefix.encode("latin1")
                stream.seek(chunk[0] ^ key)
                dimensions = png_dimensions(prefix + stream.read(max(0, 32 - len(prefix))))
                rows.append(dict(name=member, source=name, bytes=size + len(prefix),
                                 dimensions=dimensions))
    by_name = collections.defaultdict(list)
    for row in rows:
        by_name[row["name"].casefold()].append(row)
    formats = collections.Counter(Path(row["name"]).suffix.lower() for row in rows)
    images = [dict(row, rgba_mib=row["dimensions"][0] * row["dimensions"][1] * 4 / 2**20)
              for row in rows if row["dimensions"]]
    return dict(root=str(root), archives=archives, entries=len(rows), formats=formats,
                largest_files=sorted(rows, key=lambda row: row["bytes"], reverse=True)[:30],
                largest_png_surfaces=sorted(images, key=lambda row: row["rgba_mib"], reverse=True)[:30],
                case_or_overlay_collisions=[group for group in by_name.values() if len(group) > 1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), indent=2))
