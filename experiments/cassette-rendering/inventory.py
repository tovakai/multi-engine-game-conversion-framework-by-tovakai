"""Read-only PCK v1 shader feature inventory; emits no proprietary source."""
import argparse
import collections
import json
from pathlib import Path
import re
import struct


def inventory(pack):
    size = pack.stat().st_size
    with pack.open("rb") as stream:
        header = stream.read(84)
        magic, version, major, minor, patch = struct.unpack("<5I", header[:20])
        if magic != 0x43504447 or version != 1:
            raise ValueError("Only standalone PCK v1 is supported")
        count, = struct.unpack("<I", stream.read(4))
        if count > 200000:
            raise ValueError("Unreasonable entry count")
        entries = []
        for _ in range(count):
            length, = struct.unpack("<I", stream.read(4))
            if length > 16384:
                raise ValueError("Unreasonable path length")
            name = stream.read(length).rstrip(b"\0").decode("utf-8")
            offset, length = struct.unpack("<QQ", stream.read(16))
            stream.read(16)  # MD5
            if offset + length > size:
                raise ValueError("Entry outside pack")
            entries.append((name, offset, length))
        features = collections.Counter()
        shader_count = 0
        gridmap_resources = 0
        for name, offset, length in entries:
            if "gridmap" in name.lower():
                gridmap_resources += 1
            if not name.endswith(".shader") or length > 16 * 1024 * 1024:
                continue
            stream.seek(offset)
            text = stream.read(length).decode("utf-8", errors="replace")
            shader_count += 1
            for token in ("discard", "DEPTH_TEXTURE", "SCREEN_TEXTURE", "sampler2DArray",
                          "textureSize", "uint", "TIME", "INSTANCE_CUSTOM", "ALPHA_SCISSOR"):
                if re.search(r"\b" + token + r"\b", text):
                    features[token] += 1
            for mode in ("depth_draw_alpha_prepass", "depth_draw_never", "depth_test_disable",
                         "cull_disabled", "world_vertex_coords", "unshaded"):
                if re.search(r"\b" + mode + r"\b", text):
                    features["render_mode:" + mode] += 1
    return {"pack_format": version, "engine_version": f"{major}.{minor}.{patch}",
            "entries": count, "text_shader_resources": shader_count,
            "shader_feature_counts": dict(features), "gridmap_named_resources": gridmap_resources,
            "scope": "Lexical inventory; comments may match; no shader source or resources exported"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inventory(args.pack), indent=2))
