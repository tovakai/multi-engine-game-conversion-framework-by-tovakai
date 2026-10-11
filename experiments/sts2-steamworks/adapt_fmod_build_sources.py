"""Pure paired source adaptation recovered from the working FMOD build.

No installer, SDK acquisition, binary execution or backend integration is enabled.
"""

import hashlib


RECIPE_ID = "sts2-observed-fmod-build-sources-v1"
SOURCE_COMMIT = "fda1f89a08c0048ed313b333f90b7a7258ce2e61"
GODOT_CPP_COMMIT = "e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77"
RECIPES = {
    "SConstruct": (
        "253761c20fc57ba68301953ba1d11a6a355e4e6dc8663e5c0f19981dc81020f8",
        "a83e6d09efebe83ef759d40e95f8071b9a04dfa0824801ee4d6a52fdf7ea1edb",
        b'    env.Append(LINKFLAGS=["-m64", "-fuse-ld=gold"])\n',
        b'    if env["arch"] != "arm64":\n        env.Append(LINKFLAGS=["-m64", "-fuse-ld=gold"])\n',
    ),
    "src/helpers/common.h": (
        "7221a332c04b6f910ea9b27d2aaa1863243b3498341b50be2fa5d648529d607b",
        "f4f70e508e2196af5e5283279fb4bf82979ae5abb6d95c55a67492b616a1a785",
        b"#ifndef GODOTFMOD_COMMON_H\n",
        b"#include <cstdio>\n#ifndef GODOTFMOD_COMMON_H\n",
    ),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def adapt_sources(resources, *, restore=False):
    if RECIPES.keys() - resources.keys():
        raise ValueError("Missing required FMOD source file")
    hashes = {name: digest(resources[name]) for name in RECIPES}
    original = all(hashes[name] == recipe[0] for name, recipe in RECIPES.items())
    patched = all(hashes[name] == recipe[1] for name, recipe in RECIPES.items())
    if not original and not patched:
        raise ValueError("Unknown or mixed FMOD source pair")
    result = dict(resources)
    patches = []
    for name, (source, target, before, after) in RECIPES.items():
        desired = source if restore else target
        raw = resources[name]
        output = raw
        if hashes[name] != desired:
            anchor, replacement = (after, before) if restore else (before, after)
            if raw.count(anchor) != 1:
                raise ValueError("Unexpected FMOD source anchor for " + name)
            output = raw.replace(anchor, replacement, 1)
        if digest(output) != desired:
            raise ValueError("FMOD source output differs from observed bytes for " + name)
        result[name] = output
        patches.append({"path": name, "input_sha256": hashes[name], "output_sha256": desired,
                        "applied": raw != output, "size_delta_bytes": len(output) - len(raw)})
    return result, {"recipe_id": RECIPE_ID, "restore": restore, "patches": patches,
                    "scope": "Verified paired source bytes only; no writes, native build or deployment validation."}
