"""Observed STS2 deployment replay and isolated official-Linux RID candidate."""

import hashlib
import json

from inspect_dependency_graph import SOURCE_SHA256, unique_object


SOURCE_TARGET = ".NETCoreApp,Version=v9.0/win-x64"
TARGET = ".NETCoreApp,Version=v9.0/linux-arm64"
SOURCE_PACK = "runtimepack.Microsoft.NETCore.App.Runtime.win-x64/9.0.7"
TARGET_PACK = "runtimepack.Microsoft.NETCore.App.Runtime.linux-arm64/9.0.7"
SOURCE_DEPENDENCY = SOURCE_PACK.rsplit("/", 1)[0]
TARGET_DEPENDENCY = TARGET_PACK.rsplit("/", 1)[0]
GAME = "sts2/0.1.0"
NATIVE_ASSETS = (
    "createdump", "libclrgc.so", "libclrgcexp.so", "libclrjit.so", "libcoreclr.so",
    "libcoreclrtraceptprovider.so", "libhostfxr.so", "libhostpolicy.so",
    "libmscordaccore.so", "libmscordbi.so", "libSystem.Globalization.Native.so",
    "libSystem.IO.Compression.Native.so", "libSystem.Native.so",
    "libSystem.Net.Security.Native.so", "libSystem.Security.Cryptography.Native.OpenSsl.so",
)
# The official 9.0.7 framework deps and NuGet archive are fingerprinted in provenance.
LINUX_FALLBACKS = ("linux", "unix-arm64", "unix", "any", "base")
MODES = {
    "observed": {
        "fallbacks": ("win", "any", "base"),
        "sha256": "3dcc793b34e41a6a10d9a03e2f3045172abfa161a3d30ed0781d4c0a82372ffe",
        "semantic_sha256": "185ce682da780ddff6646169ce871f1ab740e53c7a41202113d7e67207f8599d",
    },
    "official-linux": {
        "fallbacks": LINUX_FALLBACKS,
        "sha256": "cbe2588f9deda53dd55c6b4788901c57483f672f3a0fec5c6ef1663ba322dcdb",
        "semantic_sha256": "b899c563cd0141f1efd8e9020419d691319920a45c7e7f72ffeaf109822df943",
    },
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(document):
    return digest(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())


def adapt_deps(raw, *, mode):
    if mode not in MODES:
        raise ValueError("Unknown deployment adaptation mode")
    recipe = MODES[mode]
    current = digest(raw)
    if current == recipe["sha256"]:
        return bytes(raw)
    if current != SOURCE_SHA256:
        raise ValueError("Unknown original dependency graph or mismatched candidate")
    document = json.loads(raw, object_pairs_hook=unique_object)
    if (document["runtimeTarget"]["name"] != SOURCE_TARGET
            or document["runtimes"] != {"win-x64": ["win", "any", "base"]}):
        raise ValueError("Unexpected source platform metadata")
    document["runtimeTarget"]["name"] = TARGET
    targets = document["targets"]
    targets[TARGET] = targets.pop(SOURCE_TARGET)
    active = targets[TARGET]
    active[TARGET_PACK] = active.pop(SOURCE_PACK)
    dependencies = active[GAME]["dependencies"]
    dependencies[TARGET_DEPENDENCY] = dependencies.pop(SOURCE_DEPENDENCY)
    active[TARGET_PACK]["native"] = {name: {} for name in NATIVE_ASSETS}
    libraries = document["libraries"]
    libraries[TARGET_PACK] = libraries.pop(SOURCE_PACK)
    document["runtimes"] = {"linux-arm64": list(recipe["fallbacks"])}
    if canonical_hash(document) != recipe["semantic_sha256"]:
        raise ValueError("Candidate dependency semantics differ from the verified recipe")
    result = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    if digest(result) != recipe["sha256"]:
        raise ValueError("Candidate dependency bytes differ from the verified recipe")
    return result
