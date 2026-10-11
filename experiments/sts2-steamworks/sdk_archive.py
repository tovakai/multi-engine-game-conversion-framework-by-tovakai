"""Import only build headers and pinned ARM64 runtimes from a vendor SDK archive."""

from pathlib import Path, PurePosixPath
import tarfile

from converter_io import safe, verified_stream, write_new

PIN = {"sha256": "48241c836b45116e1b25f9f2cb121e45c64140c5af205706b48c8b1c3712f963",
       "size_bytes": 76766958}
PREFIX = "fmodstudioapi20315linux/api/"


def prepare_sdk(source, destination):
    source = safe(source)
    if source.is_dir():
        return source
    destination = safe(destination)
    if destination.exists():
        raise ValueError("SDK extraction destination already exists")
    files = {}
    with verified_stream(source, PIN) as stream, tarfile.open(fileobj=stream, mode="r:gz") as archive:
        seen = set()
        for member in archive:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or path.as_posix() != name
                    or "\\" in name or ":" in name or name in seen):
                raise ValueError("Unsafe or duplicate SDK archive member")
            seen.add(name)
            if not name.startswith(PREFIX):
                continue
            relative = name[len(PREFIX):]
            parts = PurePosixPath(relative).parts
            header = len(parts) == 3 and parts[0] in {"core", "studio"} and parts[1] == "inc" and parts[2].endswith((".h", ".hpp"))
            library = relative in {"core/lib/arm64/libfmod.so.14.15", "studio/lib/arm64/libfmodstudio.so.14.15"}
            if not (header or library):
                continue
            if not member.isfile() or member.size > 16 * 1024 * 1024 or sum(len(v) for v in files.values()) + member.size > 32 * 1024 * 1024:
                raise ValueError("Invalid or oversized selected SDK member")
            raw = archive.extractfile(member).read(member.size + 1)
            if len(raw) != member.size:
                raise ValueError("Truncated SDK member")
            files["api/" + relative] = raw
    for name in ("api/core/lib/arm64/libfmod.so.14.15", "api/studio/lib/arm64/libfmodstudio.so.14.15"):
        if name not in files:
            raise ValueError("SDK archive lacks required ARM64 runtime")
        files[name.removesuffix(".15")] = files[name]
    destination.mkdir()
    for name, raw in files.items():
        write_new(destination / name, raw)
    return destination
