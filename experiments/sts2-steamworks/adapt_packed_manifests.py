"""Pure, exact-byte manifest adaptations recovered from the working prototype.

This is not a PCK writer or a clean-installation conversion recipe. These edits
are deliberately hash-pinned, not a generic Godot ConfigFile text rewriter.
"""

import hashlib


RECIPE_ID = "sts2-observed-packed-extension-manifests-v1"
RECIPES = {
    "addons/fmod/fmod.gdextension": (
        "d00e76c4661575ac13f205bdd1fa7482a87bc36b448dde4627ad76be501871b9",
        "573b57815b1c7e341b567e12480e735dfc9a37d5bfaf3a8bfe0a1dca5e0e93a9",
        (
            (b"[icons]\n", b'linux.release.arm64 = "res://addons/fmod/libs/linux/libGodotFmod.linux.template_release.arm64.so"\n\n[icons]\n'),
            (b"[dependencies]\n", b'[dependencies]\n\nlinux.release.arm64 = {\n    "libs/linux/libfmod.so.14": "",\n    "libs/linux/libfmodstudio.so.14": ""\n}\n\n'),
        ),
    ),
    "addons/sentry/sentry.gdextension": (
        "39ee709ec6706630a001e6a7f7116a01250751ebf2bb232c82465c9d8c63b3eb",
        "afeceb8ec9095aaac5f1ed57c2d79f152844de1bd78fd57442a0687d3da726bc",
        (
            (b'entry_symbol = "gdextension_init"', b'entry_symbol = "sentry_gdextension_init"'),
            (b"[dependencies]\n", b'linux.release.arm64 = "res://addons/sentry/bin/linux/arm64/libsentry.linux.release.arm64.so"\n\n[dependencies]\n\nlinux.arm64 = {\n    "res://addons/sentry/bin/linux/arm64/crashpad_handler" : ""\n}\n\n'),
        ),
    ),
}
UNCHANGED = {
    ".godot/extension_list.cfg": "2492b87db1ef63c4ee08a6aba5f3e5ce4e2c56f50679864621a0b54edaedcdda",
    "bin/spine_godot_extension.gdextension": "c68654b593fb6fd24997463d7fe48a3e69da531417c7eb68d782a3d95e2ed31b",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def adapt_manifest(path, raw):
    if path not in RECIPES:
        raise ValueError("No verified manifest adaptation for " + path)
    source, target, edits = RECIPES[path]
    current = digest(raw)
    if current == target:
        return raw
    if current != source:
        raise ValueError("Unknown manifest input hash for " + path)
    result = raw
    for before, after in edits:
        if result.count(before) != 1:
            raise ValueError("Unexpected manifest anchor for " + path)
        result = result.replace(before, after, 1)
    if digest(result) != target:
        raise ValueError("Manifest output differs from the device-verified bytes for " + path)
    return result


def adapt_bundle(resources):
    required = RECIPES.keys() | UNCHANGED.keys()
    missing = sorted(required - resources.keys())
    if missing:
        raise ValueError("Missing verified extension resources: " + ", ".join(missing))
    for path, expected in UNCHANGED.items():
        if digest(resources[path]) != expected:
            raise ValueError("Unexpected unchanged resource hash for " + path)
    # Construct and validate the entire dependent set before returning any changes.
    result = dict(resources)
    patches = []
    for path in RECIPES:
        original = resources[path]
        result[path] = adapt_manifest(path, original)
        patches.append({"path": path, "input_sha256": digest(original),
                        "output_sha256": digest(result[path]), "verified": True,
                        "applied": original != result[path],
                        "size_delta_bytes": len(result[path]) - len(original)})
    return result, {"recipe_id": RECIPE_ID, "patches": patches,
                    "scope": "Verified manifest bytes only; no PCK output or clean conversion validation."}
