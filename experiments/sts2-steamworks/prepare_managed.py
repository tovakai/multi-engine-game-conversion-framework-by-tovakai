"""Exact matching-build managed adaptation in memory; not a package converter."""

import struct

import patch_accessors
import patch_stats


RECIPE = "sts2-observed-matching-build-managed-v1"
WINDOWS_WRAPPER = "e1cd0bf2436cefbb8bfcfcc1cea0587e5b9c740769e8340f7b9e9de72785fcf0"
WINDOWS_GAME = "bdf10e3bc572d0061c7d523b8f2ff4aa998baa19bd8cac5e2474b87cbe6500ab"


def arm64_metadata(data, expected_source, expected_target):
    if patch_stats.sha256(data) != expected_source:
        raise ValueError("Unknown original managed input hash")
    if data[:2] != b"MZ" or len(data) < 64:
        raise ValueError("Expected a PE image")
    header = struct.unpack_from("<I", data, 60)[0]
    if (header + 26 > len(data) or data[header:header + 4] != b"PE\0\0"
            or data[header + 4:header + 6] != b"\x64\x86"
            or data[header + 24:header + 26] != b"\x0b\x02"):
        raise ValueError("Expected the inspected AMD64 PE32+ metadata")
    # Only the exact images whose ARM64 counterparts were inspected are allowed.
    # Changing this field is not native-code translation or a general PE recipe.
    result = data[:header + 4] + b"\x64\xaa" + data[header + 6:]
    if patch_stats.sha256(result) != expected_target:
        raise ValueError("Metadata adaptation differs from the inspected counterpart")
    return result


def prepare_pair(game, wrapper):
    original = (patch_stats.sha256(game), patch_stats.sha256(wrapper))
    target = (patch_stats.GAME_TARGET, patch_stats.WRAPPER_TARGET)
    if original == target:
        return {"sts2.dll": bytes(game), "Steamworks.NET.dll": bytes(wrapper)}
    if original != (WINDOWS_GAME, WINDOWS_WRAPPER):
        raise ValueError("Expected the verified original pair or complete final pair")
    game = arm64_metadata(game, WINDOWS_GAME, patch_stats.GAME_SOURCE)
    wrapper = arm64_metadata(wrapper, WINDOWS_WRAPPER, patch_accessors.ORIGINAL_SHA256)
    wrapper = patch_accessors.patched_bytes(wrapper, "generic-v1")
    wrapper = patch_accessors.patched_bytes(wrapper, "client023-v2")
    wrapper = patch_stats.patched_bytes(wrapper, patch_stats.RECIPES[0])
    game = patch_stats.patched_bytes(game, patch_stats.RECIPES[1])
    if (patch_stats.sha256(game), patch_stats.sha256(wrapper)) != target:
        raise ValueError("Final managed pair hash mismatch")
    return {"sts2.dll": game, "Steamworks.NET.dll": wrapper}
