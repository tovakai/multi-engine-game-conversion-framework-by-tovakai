"""Single release authority and portable source/build identity (no runtime dependencies)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import re
import subprocess
import sys

# Change only when preparing a deliberate public release, not on every commit.
RELEASE_VERSION = "0.1.1.2"
ROOT = Path(__file__).resolve().parents[1]
EMBEDDED = Path(__file__).with_name("_build_info.json")


def parse_release(value: str) -> tuple[int, int, int, int]:
    """Accept the existing three-part releases and four-part public convention."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))?", value):
        raise ValueError(f"Invalid application release version: {value!r}")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) if len(parts) == 3 else parts


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-c", "core.safecrlf=false", *args],
                                   cwd=root, stderr=subprocess.DEVNULL, text=True,
                                   timeout=15).strip()


def resolve_source(root: Path = ROOT) -> dict:
    """Root commit count is independent of tags; SHA disambiguates forks/merges."""
    parse_release(RELEASE_VERSION)
    info = dict(schema="megcfbt.build/v1", release_version=RELEASE_VERSION,
                version=f"{RELEASE_VERSION}.dev0+unknown", build_kind="unknown",
                development_id=None, commit=None, short_commit=None,
                tracked_changes=None, tracked_diff_sha256=None, shallow=None,
                commit_count=None, platform=None, architecture=platform.machine(),
                built_utc=None, metadata_status="Git metadata unavailable")
    try:
        # Never borrow the identity of an unrelated enclosing repository.
        if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
            return info
        commit = _git(root, "rev-parse", "HEAD")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return info
        shallow = _git(root, "rev-parse", "--is-shallow-repository") == "true"
        # Includes staged and unstaged changes, excludes untracked runtime/cache files.
        dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
        diff_digest = None
        if dirty:
            diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=root,
                                           stderr=subprocess.DEVNULL, timeout=15)
            diff_digest = hashlib.sha256(diff).hexdigest()
        tags = _git(root, "tag", "--points-at", "HEAD").splitlines()
        count = None if shallow else int(_git(root, "rev-list", "--count", "HEAD"))
        released = f"v{RELEASE_VERSION}" in tags and not dirty and not shallow
        local = f"g{commit[:12]}" + (".shallow" if shallow else "")
        if dirty:
            local += f".dirty.d{diff_digest[:12]}"
        version = RELEASE_VERSION if released else f"{RELEASE_VERSION}.dev{count or 0}+{local}"
        info.update(version=version, build_kind="release" if released else "development",
                    development_id=None if released else version, commit=commit,
                    short_commit=commit[:12], tracked_changes=dirty, shallow=shallow,
                    tracked_diff_sha256=diff_digest, commit_count=count,
                    metadata_status="complete" if not shallow else "shallow history; commit count unavailable")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return info


def read_build_info() -> dict:
    """Frozen/installed distributions use embedded metadata without invoking Git."""
    # A source checkout always resolves its current state, ignoring stale build files.
    if not getattr(sys, "frozen", False) and (ROOT / ".git").exists():
        return resolve_source()
    try:
        info = json.loads(EMBEDDED.read_text(encoding="utf-8"))
        if (info["schema"] != "megcfbt.build/v1" or info["release_version"] != RELEASE_VERSION
                or not isinstance(info["version"], str)
                or not set(unknown_build_info()).issubset(info)
                or info['build_kind'] not in {'unknown', 'development', 'release'}
                or (info['commit'] is not None and not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', info['commit']))
                or (info['build_kind'] == 'release' and
                    (info['version'] != RELEASE_VERSION or info['tracked_changes'] is not False or not info['commit']))):
            raise ValueError("Invalid embedded build identity")
        return info
    except (OSError, ValueError, KeyError, TypeError):
        return resolve_source() if not getattr(sys, "frozen", False) else unknown_build_info()


def unknown_build_info() -> dict:
    # An absent frozen identity must never pick up Git from the user's machine.
    info = dict(schema="megcfbt.build/v1", release_version=RELEASE_VERSION,
                version=f"{RELEASE_VERSION}.dev0+unknown", build_kind="unknown",
                development_id=None, commit=None, short_commit=None, tracked_changes=None,
                tracked_diff_sha256=None, shallow=None, commit_count=None, platform=None,
                architecture=platform.machine(), built_utc=None,
                metadata_status="Embedded build metadata unavailable")
    return info


def validate_release(tag: str, info: dict) -> None:
    parse_release(tag.removeprefix("v"))
    if tag != f"v{RELEASE_VERSION}":
        raise ValueError(f"Release tag {tag!r} does not match v{RELEASE_VERSION}")
    if (info.get("tracked_changes") is not False or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', info.get('commit') or '')
            or info.get("shallow") is not False or info.get("build_kind") != "release"
            or info.get("version") != RELEASE_VERSION):
        raise ValueError("Official releases require a clean, fully fetched checkout at the matching tag")


def packaged_build_info(target: str | None = None) -> dict:
    info = get_build_info().copy()
    info.update(platform=target, architecture={"windows-x64": "x86_64", "linux-aarch64": "aarch64", "linux-x64": "x86_64"}.get(target, platform.machine()),
                built_utc=utc_now())
    return info


def display_version(info: dict | None = None) -> str:
    info = get_build_info() if info is None else info
    label = "v" + info["version"].split("+")[0]
    if info.get("short_commit") and info["build_kind"] != "release":
        label += f" ({info['short_commit']})"
    if info.get("tracked_changes"):
        label += " [dirty]"
    if info["build_kind"] == "unknown":
        label += " [source unknown]"
    return label


_BUILD_INFO = read_build_info()
__version__ = _BUILD_INFO['version']


def get_build_info() -> dict:
    """One startup snapshot shared by every consumer in this process."""
    return _BUILD_INFO.copy()
