"""Compare PCK v1 directory digests without exporting any game resources."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct


def index(path):
    entries = {}
    with path.open("rb") as stream:
        header = stream.read(84)
        magic, version = struct.unpack("<II", header[:8])
        if magic != 0x43504447 or version != 1:
            raise ValueError("Requires standalone PCK v1")
        count, = struct.unpack("<I", stream.read(4))
        if count > 200000:
            raise ValueError("Unreasonable entry count")
        for _ in range(count):
            length, = struct.unpack("<I", stream.read(4))
            if length > 16384:
                raise ValueError("Unreasonable path length")
            name = stream.read(length).rstrip(b"\0").decode("utf-8")
            stream.read(16)  # offset and size
            entries[name] = stream.read(16).hex()
    return entries


def compare(left, right):
    a, b = index(left), index(right)
    common = a.keys() & b.keys()
    different = [name for name in common if a[name] != b[name]]
    shaders = [name for name in common if name.endswith(".shader")]
    return {"left_entries": len(a), "right_entries": len(b),
            "common": len(common), "different_digest": len(different),
            "left_only": len(a.keys() - b.keys()), "right_only": len(b.keys() - a.keys()),
            "different_by_extension": dict(Counter(Path(name).suffix for name in different)),
            "shared_shader_resources": len(shaders),
            "different_shader_digests": sum(a[name] != b[name] for name in shaders),
            "project_binary_digest_equal": a.get("res://project.binary") == b.get("res://project.binary"),
            "scope": "Pack-directory MD5 comparison; no resources extracted or distributed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(compare(args.left, args.right), indent=2))
