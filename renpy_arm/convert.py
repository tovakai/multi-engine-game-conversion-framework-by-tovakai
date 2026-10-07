"""Ren'Py → Linux aarch64 conversion core (pure Python)."""
from __future__ import annotations

import hashlib
import marshal
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .profiles import (
    ProfileError,
    detect_legacy_version,
    detect_profile,
    is_legacy_renpy_game,
    migrate_profile,
)

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, Optional[float], Optional[str]], None]

HELPER_SH = {
    "make-linux-arm.sh",
    "launch-steam.sh",
    "add-to-steam.sh",
    "diagnose-frame.sh",
    "make-rpgmaker-arm.sh",
}

VER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:\.\d+)?")

# These final releases are known to have had packaging/build problems. The
# immediate fix releases are safer ARM runtime targets and preserve the same
# Ren'Py/Python compatibility line.
ARM_RUNTIME_REDIRECTS = {
    # 7.5.0/7.5.1 and 8.0.0/8.0.1 predate the aarch64 launch fix that
    # landed in the paired 7.5.2/8.0.2 release. Use the final fix release of
    # each line rather than shipping a runtime known to be shaky on ARM64.
    "7.5.0": "7.5.3",
    "7.5.1": "7.5.3",
    "8.0.0": "8.0.3",
    "8.0.1": "8.0.3",

    # These paired releases had a general build problem fixed immediately by
    # 7.7.3/8.2.3.
    "7.7.2": "7.7.3",
    "8.2.2": "8.2.3",
}


@dataclass
class ConvertResult:
    game_dir: Path
    game_name: str
    version: str
    archive_path: Optional[Path]
    messages: list[str] = field(default_factory=list)


class ConvertError(Exception):
    pass


def _log(log: Optional[LogFn], msg: str) -> None:
    if log:
        log(msg)


def _progress(
    progress: Optional[ProgressFn],
    stage: str,
    fraction: Optional[float] = None,
    detail: Optional[str] = None,
) -> None:
    if progress:
        if fraction is not None:
            fraction = max(0.0, min(1.0, fraction))
        progress(stage, fraction, detail)


def _human_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def normalize_version(s: str) -> Optional[str]:
    m = VER_RE.search(s.strip().strip("'\""))
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return None


def find_launcher_sh(game_dir: Path) -> Path:
    sh_files = sorted(game_dir.glob("*.sh"))
    preferred = []
    fallback = []
    for f in sh_files:
        if f.name in HELPER_SH:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "RENPY_PLATFORM" in text:
            preferred.append(f)
        else:
            fallback.append(f)
    if preferred:
        return preferred[0]
    if fallback:
        return fallback[0]
    raise ConvertError("No Ren'Py .sh launcher found (expected a script with RENPY_PLATFORM).")


def detect_python_tag(game_dir: Path, version: Optional[str] = None) -> str:
    """Detect whether this distribution needs the Python 2 or Python 3 runtime.

    Ren'Py 7.x is Python 2 and Ren'Py 8.x is Python 3. Newer distributions
    usually encode that in lib/py2-* or lib/py3-* directory names, but older
    7.x builds can use pre-prefix runtime directory names. In ambiguous layouts,
    use the detected Ren'Py major version instead of defaulting old games to
    Python 3.
    """
    lib = game_dir / "lib"
    has_py2 = any(lib.glob("py2-*")) if lib.is_dir() else False
    has_py3 = any(lib.glob("py3-*")) if lib.is_dir() else False

    if has_py2 and not has_py3:
        return "py2"
    if has_py3 and not has_py2:
        return "py3"

    if version:
        normalized = normalize_version(version)
        if normalized:
            major = int(normalized.split(".", 1)[0])
            if major <= 7:
                return "py2"
            if major >= 8:
                return "py3"

    # Modern Ren'Py is Python 3, so keep py3 as the final fallback only when
    # neither the runtime layout nor version metadata can disambiguate it.
    return "py3"


def _from_py_source(path: Path) -> Optional[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"""(?m)^version\s*=\s*(['\"])(.*?)\1""", text)
    if m:
        n = normalize_version(m.group(2))
        if n:
            return n
    m = re.search(
        r"""(?m)^vc_version\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)""",
        text,
    )
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    m = re.search(
        r"""(?m)^version_tuple\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)""",
        text,
    )
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    for m in re.finditer(r"""['\"](\d+\.\d+\.\d+(?:\.\d+)?)['\"]""", text):
        n = normalize_version(m.group(1))
        if n:
            return n
    return None


def _load_pyc_code(path: Path):
    data = path.read_bytes()
    for skip in (16, 12, 8):
        try:
            return marshal.loads(data[skip:])
        except Exception:
            continue
    return None


def _from_pyc(path: Path) -> Optional[str]:
    code = _load_pyc_code(path)
    if code is None:
        return None
    found: list[str] = []

    def walk(c):
        for x in c.co_consts:
            if isinstance(x, str):
                n = normalize_version(x)
                if n:
                    found.append(n)
            elif hasattr(x, "co_consts"):
                walk(x)

    walk(code)
    return found[0] if found else None


def detect_version(game_dir: Path, override: Optional[str] = None) -> str:
    if override:
        n = normalize_version(override)
        if not n:
            raise ConvertError(f"Invalid version override: {override}")
        return n

    # Modern Ren'Py distributions can include the exact script/runtime version
    # tuple as game/script_version.txt, for example "(8, 4, 1)". Prefer this
    # distribution metadata when present.
    script_version = game_dir / "game" / "script_version.txt"
    if script_version.is_file():
        try:
            text = script_version.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(
            r"\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)",
            text,
        )
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    for path in (
        game_dir / "renpy" / "vc_version.py",
        game_dir / "renpy" / "versions.py",
        game_dir / "renpy" / "__init__.py",
    ):
        if path.is_file():
            n = _from_py_source(path)
            if n:
                return n

    candidates = [
        game_dir / "renpy" / "vc_version.pyc",
        game_dir / "renpy" / "versions.pyc",
    ]
    pycache = game_dir / "renpy" / "__pycache__"
    if pycache.is_dir():
        candidates.extend(sorted(pycache.glob("vc_version.cpython-*.pyc")))
        candidates.extend(sorted(pycache.glob("versions.cpython-*.pyc")))
    for path in candidates:
        if path.is_file():
            n = _from_pyc(path)
            if n:
                return n

    raise ConvertError(
        "Could not detect Ren'Py version from the bundled engine metadata. "
        "Set the version manually."
    )


def is_modern_renpy_game(game_dir: Path) -> bool:
    return (game_dir / "renpy").is_dir() and (game_dir / "lib").is_dir()


def is_renpy_game(game_dir: Path) -> bool:
    """Recognize both modern distributions and supported legacy layouts."""
    return is_modern_renpy_game(game_dir) or is_legacy_renpy_game(game_dir)


def resolve_conversion_version(
    game_dir: Path,
    version_override: Optional[str] = None,
    profile_match=None,
) -> str:
    """Resolve the runtime version for the final normalized game tree.

    An explicit user override wins. A compatibility profile's pinned target
    version is authoritative for the tree produced by that profile, even when
    the packaged reference build omits source-form engine version metadata.
    """
    if version_override:
        return detect_version(game_dir, version_override)

    if profile_match is not None:
        target = normalize_version(profile_match.profile.target_version)
        if not target:
            raise ConvertError(
                f"Compatibility profile {profile_match.profile.id} has an invalid "
                f"target Ren'Py version: {profile_match.profile.target_version}"
            )
        return target

    return detect_version(game_dir)


def _safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in zf.infolist():
        target = (destination / member.filename).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ConvertError(f"Unsafe path in zip archive: {member.filename}") from exc
    zf.extractall(destination)


def _safe_extract_tar(tf: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tf.getmembers():
        target = (destination / member.name).resolve()
        try:
            target.relative_to(destination)

            if member.issym():
                link_target = (target.parent / member.linkname).resolve()
                link_target.relative_to(destination)
            elif member.islnk():
                link_target = (destination / member.linkname).resolve()
                link_target.relative_to(destination)
        except ValueError as exc:
            raise ConvertError(f"Unsafe path in tar archive: {member.name}") from exc
    tf.extractall(destination)


def default_cache_dir() -> Path:
    """Return a persistent per-user cache for SDKs and compatibility assets."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "RenFrame" / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "renframe"
    return Path.home() / ".cache" / "renframe"


def resolve_input(path: Path, work_root: Path, log: Optional[LogFn] = None) -> Path:
    """Return a game directory. Archives are extracted under work_root."""
    path = path.resolve()
    if path.is_dir():
        if is_renpy_game(path):
            return path
        # nested single folder
        kids = [p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if len(kids) == 1 and is_renpy_game(kids[0]):
            return kids[0]
        raise ConvertError(f"Not a recognizable Ren'Py game folder: {path}")

    if not path.is_file():
        raise ConvertError(f"Path not found: {path}")

    suffix = path.suffix.lower()
    extract_dir = work_root / f"extract-{path.stem}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    _log(log, f"Extracting archive {path.name}…")
    if suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            _safe_extract_zip(zf, extract_dir)
    elif suffix in {".gz", ".bz2", ".xz"} or path.name.endswith((".tar.gz", ".tar.bz2", ".tgz")):
        with tarfile.open(path, "r:*") as tf:
            _safe_extract_tar(tf, extract_dir)
    elif suffix == ".7z":
        raise ConvertError("`.7z` input is not supported yet — use .zip or a folder.")
    else:
        raise ConvertError(f"Unsupported archive type: {path.name}")

    if is_renpy_game(extract_dir):
        return extract_dir
    # common: archive contains one top-level folder
    kids = [p for p in extract_dir.iterdir() if p.is_dir()]
    for kid in kids:
        if is_renpy_game(kid):
            return kid
    raise ConvertError("Archive did not contain a recognizable Ren'Py game.")


def download_sdk(
    version: str,
    cache_dir: Path,
    force: bool,
    log: Optional[LogFn] = None,
    progress: Optional[ProgressFn] = None,
) -> tuple[Path, str]:
    """Download an ARM SDK, with a conservative same-series fallback.

    Some commercial games are built with Ren'Py nightlies whose semantic patch
    version was never published as a final SDK. For example, an 8.4.2 nightly
    exists in the wild even though the final 8.4 series stops at 8.4.1.
    If the exact sdkarm URL returns HTTP 404, try earlier patch releases in the
    same major.minor series. Never cross a minor-version boundary silently.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    normalized = normalize_version(version)
    if not normalized:
        raise ConvertError(f"Invalid Ren'Py version: {version}")

    major, minor, patch = (int(i) for i in normalized.split("."))

    bridge_runtime = None
    redirected_runtime = ARM_RUNTIME_REDIRECTS.get(normalized)
    if redirected_runtime:
        candidates = [redirected_runtime]
        _log(
            log,
            f"Ren'Py {normalized} has a known broken release build; "
            f"using fixed runtime {redirected_runtime}",
        )
        _progress(
            progress,
            "Downloading runtime",
            0.0,
            f"{normalized} → {redirected_runtime} fixed runtime",
        )
    elif major == 7 and minor == 4:
        # Linux aarch64 support first landed in Ren'Py 7.5. Ren'Py 7.5 is the
        # Python 2.7 continuation of the 7.x line, so it is the narrowest
        # generic compatibility bridge for 7.4 games.
        bridge_runtime = "7.5.3"
        candidates = [bridge_runtime]
        _log(
            log,
            f"Ren'Py {normalized} predates Linux ARM64 support; "
            f"trying compatibility runtime {bridge_runtime}",
        )
        _progress(
            progress,
            "Downloading runtime",
            0.0,
            f"7.4.x → {bridge_runtime} ARM compatibility runtime",
        )
    elif major < 7 or (major == 7 and minor < 4):
        raise ConvertError(
            f"Ren'Py {normalized} predates Linux ARM64 support and is too old "
            "for RenFrame's generic runtime bridge. This game needs a "
            "compatibility profile."
        )
    else:
        candidates = [
            f"{major}.{minor}.{candidate_patch}"
            for candidate_patch in range(patch, -1, -1)
        ]

    last_404 = None
    for candidate in candidates:
        name = f"renpy-{candidate}-sdkarm.tar.bz2"
        url = f"https://www.renpy.org/dl/{candidate}/{name}"
        dest = cache_dir / name

        if dest.is_file() and not force:
            if bridge_runtime:
                _log(
                    log,
                    f"Using cached Ren'Py {candidate} ARM compatibility runtime "
                    f"for Ren'Py {normalized}",
                )
            elif redirected_runtime:
                _log(
                    log,
                    f"Using cached fixed Ren'Py {candidate} ARM runtime "
                    f"for problematic {normalized}",
                )
            elif candidate != normalized:
                _log(
                    log,
                    f"Exact ARM SDK for Ren'Py {normalized} is unavailable; "
                    f"using cached {candidate} from the same release series",
                )
            else:
                _log(log, f"Using cached SDK: {dest.name}")
            _progress(progress, "Downloading runtime", 1.0, f"Cached {dest.name}")
            return dest, candidate

        _log(log, f"Downloading {url}")
        _progress(progress, "Downloading runtime", 0.0, name)
        partial = dest.with_suffix(dest.suffix + ".partial")

        def reporthook(blocks: int, block_size: int, total_size: int) -> None:
            downloaded = blocks * block_size
            if total_size > 0:
                downloaded = min(downloaded, total_size)
                fraction = downloaded / total_size
                detail = f"{name}  ·  {_human_bytes(downloaded)} / {_human_bytes(total_size)}"
            else:
                fraction = None
                detail = f"{name}  ·  {_human_bytes(downloaded)}"
            _progress(progress, "Downloading runtime", fraction, detail)

        try:
            urllib.request.urlretrieve(url, partial, reporthook=reporthook)
        except urllib.error.HTTPError as exc:
            try:
                partial.unlink()
            except OSError:
                pass
            if exc.code == 404:
                last_404 = exc
                if candidate != candidates[-1]:
                    _log(
                        log,
                        f"No published ARM SDK for Ren'Py {candidate}; "
                        "trying the previous patch release",
                    )
                    _progress(
                        progress,
                        "Downloading runtime",
                        0.0,
                        f"{candidate} unavailable; trying previous patch",
                    )
                continue
            raise ConvertError(
                f"Failed to download SDK for Ren'Py {candidate}.\n{exc}\n"
                f"Check https://www.renpy.org/dl/{candidate}/"
            ) from exc
        except Exception as exc:
            try:
                partial.unlink()
            except OSError:
                pass
            raise ConvertError(
                f"Failed to download SDK for Ren'Py {candidate}.\n{exc}\n"
                f"Check https://www.renpy.org/dl/{candidate}/"
            ) from exc

        partial.replace(dest)
        if bridge_runtime:
            _log(
                log,
                f"WARNING: Ren'Py {normalized} predates Linux ARM64 support. "
                f"Using Ren'Py {candidate}, the Python 2.7 ARM compatibility "
                "runtime. Game-specific incompatibilities may still require a "
                "compatibility profile.",
            )
        elif redirected_runtime:
            _log(
                log,
                f"Ren'Py {normalized} is redirected to fixed ARM runtime "
                f"{candidate}.",
            )
        elif candidate != normalized:
            _log(
                log,
                f"WARNING: Ren'Py {normalized} has no published ARM SDK. "
                f"Using {candidate} from the same {major}.{minor}.x series. "
                "Nightly-only engine changes may still require a newer runtime.",
            )
        return dest, candidate

    if bridge_runtime:
        raise ConvertError(
            f"Ren'Py {normalized} predates Linux ARM64 support, and the "
            f"{bridge_runtime} compatibility runtime could not be downloaded."
        ) from last_404

    raise ConvertError(
        f"No published ARM SDK found for Ren'Py {normalized} or an earlier "
        f"{major}.{minor}.x patch release."
    ) from last_404


def verify_sdk_checksum(sdk_file: Path, version: str, log: Optional[LogFn] = None) -> None:
    url = f"https://www.renpy.org/dl/{version}/checksums.txt"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        _log(log, "No checksums.txt — skipping verify")
        return

    section = None
    expected = None
    name = sdk_file.name
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("# sha256"):
            section = "sha256"
            continue
        if s.startswith("#"):
            section = s.lower().lstrip("#").strip() or section
            continue
        if name not in s:
            continue
        m = re.match(r"^([a-fA-F0-9]+)\s+\S+", s)
        if not m:
            continue
        digest = m.group(1).lower()
        if section == "sha256" and len(digest) == 64:
            expected = digest
            break
        if expected is None and len(digest) == 64:
            expected = digest
    if not expected:
        _log(log, "Could not parse SHA256 — skipping verify")
        return
    got = hashlib.sha256(sdk_file.read_bytes()).hexdigest()
    if got != expected:
        raise ConvertError(f"SHA256 mismatch for {name}\nexpected: {expected}\ngot: {got}")
    _log(log, "Checksum OK")


def extract_aarch64(
    sdk_file: Path,
    game_dir: Path,
    python_tag: str,
    game_name: str,
    log: Optional[LogFn] = None,
) -> Path:
    dest = game_dir / "lib" / f"{python_tag}-linux-aarch64"
    needle = f"/lib/{python_tag}-linux-aarch64"
    _log(log, f"Extracting {python_tag}-linux-aarch64 from SDK…")
    with tempfile.TemporaryDirectory(prefix="renpy-sdk-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(sdk_file, "r:bz2") as tf:
            members = [m for m in tf.getmembers() if needle in m.name.replace("\\", "/")]
            if not members:
                raise ConvertError(
                    f"SDK missing lib/{python_tag}-linux-aarch64 — "
                    "this Ren'Py version may not ship ARM."
                )
            tf.extractall(tmp_path, members=members)
        found = list(tmp_path.rglob(f"{python_tag}-linux-aarch64"))
        found = [p for p in found if p.is_dir()]
        if not found:
            raise ConvertError("Extract failed — platform directory not found")
        src = found[0]
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    renpy_bin = dest / "renpy"
    py_bin = dest / "python"
    named = dest / game_name
    if renpy_bin.is_file():
        shutil.copy2(renpy_bin, named)
    elif py_bin.is_file():
        shutil.copy2(py_bin, named)
    else:
        _log(log, "WARNING: No renpy/python binary in aarch64 lib")
    for p in dest.iterdir():
        try:
            p.chmod(p.stat().st_mode | 0o111)
        except OSError:
            pass
    _log(log, f"Installed: {dest}")
    return dest


def sync_engine_from_sdk(
    sdk_file: Path,
    game_dir: Path,
    source_version: str,
    runtime_version: str,
    log: Optional[LogFn] = None,
) -> None:
    """Keep Ren'Py Python code and compiled ARM runtime on the same release.

    librenpython.so is a Cython extension tightly coupled to the Python modules
    in the Ren'Py engine tree. Mixing an ARM runtime from one Ren'Py release
    with renpy/ from another can boot far enough to produce misleading runtime
    errors (for example missing Cache methods) before game start.

    When RenFrame intentionally selects a different compatible runtime release,
    replace only the copied conversion's engine tree with the matching SDK
    engine. Game content under game/ is left untouched.
    """
    if normalize_version(source_version) == normalize_version(runtime_version):
        return

    _log(
        log,
        f"Synchronizing Ren'Py engine {source_version} → {runtime_version} "
        "to match the selected ARM runtime",
    )

    with tempfile.TemporaryDirectory(prefix="renpy-engine-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(sdk_file, "r:bz2") as tf:
            members = tf.getmembers()

            # Find the SDK's top-level renpy package from renpy/__init__.py,
            # then extract that whole package. This avoids depending on the
            # archive's versioned root directory name.
            init_members = [
                m
                for m in members
                if m.isfile()
                and m.name.replace("\\", "/").endswith("/renpy/__init__.py")
            ]
            if not init_members:
                raise ConvertError(
                    f"SDK for Ren'Py {runtime_version} does not contain a "
                    "recognizable renpy/ engine tree."
                )

            init_name = init_members[0].name.replace("\\", "/")
            renpy_prefix = init_name[: -len("/__init__.py")]
            engine_members = [
                m
                for m in members
                if (
                    m.name.replace("\\", "/") == renpy_prefix
                    or m.name.replace("\\", "/").startswith(renpy_prefix + "/")
                )
            ]
            tf.extractall(tmp_path, members=engine_members)

        extracted = tmp_path / Path(renpy_prefix)
        if not extracted.is_dir():
            raise ConvertError(
                f"Failed to extract Ren'Py {runtime_version} engine tree."
            )

        dest = game_dir / "renpy"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(extracted), str(dest))

    _log(log, f"Installed matching Ren'Py {runtime_version} engine tree")


def sync_runtime_support_from_sdk(
    sdk_file: Path,
    game_dir: Path,
    python_tag: str,
    runtime_version: str,
    log: Optional[LogFn] = None,
) -> None:
    """Overlay shared SDK runtime support needed by the selected ARM build.

    Ren'Py SDKs can keep architecture-neutral Python support files next to,
    rather than inside, lib/<python>-linux-aarch64. Copying only the ARM
    platform directory can therefore leave a bridged game with an older
    standard library. Ren'Py 7.5, for example, imports the Python 2 typing
    backport from this shared runtime support.

    Only architecture-neutral children of the SDK's lib/ directory are merged.
    Other platform runtimes are deliberately ignored.
    """
    selected_platform = f"{python_tag}-linux-aarch64"

    with tempfile.TemporaryDirectory(prefix="renpy-runtime-support-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(sdk_file, "r:bz2") as tf:
            members = tf.getmembers()
            marker_suffix = f"/lib/{selected_platform}/librenpython.so"
            markers = [
                m.name.replace("\\", "/")
                for m in members
                if m.isfile()
                and m.name.replace("\\", "/").endswith(marker_suffix)
            ]
            if not markers:
                raise ConvertError(
                    f"SDK for Ren'Py {runtime_version} does not contain "
                    f"lib/{selected_platform}/librenpython.so."
                )

            marker_name = markers[0]
            lib_prefix = marker_name[: -len(f"/{selected_platform}/librenpython.so")]

            def shared_member(member) -> bool:
                name = member.name.replace("\\", "/")
                if not name.startswith(lib_prefix + "/"):
                    return False
                rel = name[len(lib_prefix) + 1 :]
                if not rel:
                    return False
                first = rel.split("/", 1)[0]
                if first == selected_platform:
                    return False
                if first.startswith(("py2-", "py3-")):
                    return False
                if first.startswith(("linux-", "windows-", "mac-", "darwin-")):
                    return False
                return True

            shared = [m for m in members if shared_member(m)]
            if not shared:
                _log(
                    log,
                    f"No shared runtime support found in Ren'Py {runtime_version} SDK",
                )
                return
            tf.extractall(tmp_path, members=shared)

        src_lib = tmp_path / Path(lib_prefix)
        dest_lib = game_dir / "lib"
        dest_lib.mkdir(parents=True, exist_ok=True)

        copied = 0
        for child in src_lib.iterdir():
            dest = dest_lib / child.name
            if child.is_dir():
                shutil.copytree(child, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(child, dest)
            copied += 1

    _log(
        log,
        f"Merged Ren'Py {runtime_version} shared runtime support "
        f"({copied} lib entries)",
    )


def normalize_shell_script(path: Path, log: Optional[LogFn] = None) -> bool:
    """Normalize a shell script to Unix LF endings.

    RenFrame commonly runs on Windows, while the resulting package is executed
    on Linux. A CRLF shebang becomes /bin/sh^M on Linux and cannot be executed.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return False

    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized == data:
        return False

    path.write_bytes(normalized)
    _log(log, f"Normalized LF line endings: {path.name}")
    return True


def patch_launcher_sh(
    launcher: Path,
    python_tag: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> None:
    normalize_shell_script(launcher, log=log)
    text = launcher.read_text(encoding="utf-8", errors="replace")

    # Older Ren'Py 7 launchers look up lib/$RENPY_PLATFORM directly, while
    # newer launchers add the py2-/py3- prefix separately. If we inject plain
    # linux-aarch64 into an old launcher it searches lib/linux-aarch64 even
    # though the ARM SDK runtime lives in lib/py2-linux-aarch64.
    bare_platform_lookup = bool(
        re.search(
            r'''LIB=["']?\$ROOT/lib/\$\{?RENPY_PLATFORM\}?["']?''',
            text,
        )
    )
    arm_platform = (
        f"{python_tag}-linux-aarch64"
        if bare_platform_lookup and python_tag
        else "linux-aarch64"
    )

    arm_case_re = re.compile(
        r'(?ms)(^[ \t]*\*-aarch64\|\*-arm64\)[ \t]*\n'
        r'.*?^[ \t]*;;[ \t]*$)'
    )
    existing = arm_case_re.search(text)
    if existing:
        block = existing.group(1)
        desired = re.sub(
            r'RENPY_PLATFORM=["\'][^"\']+["\']',
            f'RENPY_PLATFORM="{arm_platform}"',
            block,
            count=1,
        )
        if desired != block:
            bak = launcher.with_suffix(launcher.suffix + ".bak-before-arm")
            if not bak.exists():
                bak.write_text(text, encoding="utf-8")
            launcher.write_text(
                text[: existing.start(1)] + desired + text[existing.end(1) :],
                encoding="utf-8",
                newline="\n",
            )
            _log(log, f"Updated ARM platform mapping in {launcher.name} → {arm_platform}")
        else:
            _log(log, "Launcher already maps aarch64/arm64 correctly")
        return

    snippet = (
        '        *-aarch64|*-arm64)\n'
        f'            RENPY_PLATFORM="{arm_platform}"\n'
        "            ;;\n"
    )
    new, n = re.subn(
        r"(^[ \t]*Linux-\*\)[ \t]*\n)",
        snippet + r"\1",
        text,
        count=1,
        flags=re.M,
    )
    if n == 0:
        _log(log, "WARNING: Could not auto-patch launcher — unexpected format")
        return
    bak = launcher.with_suffix(launcher.suffix + ".bak-before-arm")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")
    launcher.write_text(new, encoding="utf-8", newline="\n")
    _log(log, f"Patched {launcher.name} → {arm_platform}")


def write_frame_diagnostics(game_dir: Path, game_name: str, log: Optional[LogFn] = None) -> Path:
    diag = game_dir / "diagnose-frame.sh"
    diag.write_text(
        f"""#!/usr/bin/env bash
set -u
GAME_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$GAME_DIR"

echo "=== RenFrame launch diagnostics ==="
echo "game_dir=$GAME_DIR"
echo "uname=$(uname -a)"
echo "machine=$(uname -m)"
echo

echo "=== launchers ==="
ls -l ./*.sh 2>/dev/null || true
echo

echo "=== ARM runtime ==="
for runtime in \\
    "$GAME_DIR"/lib/*-linux-aarch64/renpy \\
    "$GAME_DIR"/lib/*-linux-aarch64/python \\
    "$GAME_DIR"/lib/*-linux-aarch64/{game_name}; do
    if [[ -f "$runtime" ]]; then
        chmod +x "$runtime" 2>/dev/null || true
        ls -l "$runtime"
        command -v file >/dev/null 2>&1 && file "$runtime" || true
    fi
done
echo

echo "=== librenpython dependencies ==="
for so in "$GAME_DIR"/lib/*-linux-aarch64/librenpython.so; do
    [[ -f "$so" ]] || continue
    echo "-- $so"
    if command -v ldd >/dev/null 2>&1; then
        ldd "$so" 2>&1 | grep -E 'not found|=>' || true
    else
        echo "ldd not installed"
    fi
done
echo

echo "=== platform-selection lines ==="
grep -nE 'RENPY_PLATFORM|Linux-\\*|linux-aarch64|aarch64|arm64' ./*.sh 2>/dev/null || true
echo

echo "=== Ren'Py logs already present ==="
find "$GAME_DIR" -maxdepth 2 -type f \\( -name 'traceback.txt' -o -name 'log.txt' -o -name 'errors.txt' \\) -print 2>/dev/null || true
echo

if [[ "${{1:-}}" == "--launch" ]]; then
    echo "=== traced launch ==="
    exec bash -x "$GAME_DIR/launch-steam.sh"
fi

echo "Run ./diagnose-frame.sh --launch to trace an actual launch."
""",
        encoding="utf-8",
        newline="\n",
    )
    try:
        diag.chmod(diag.stat().st_mode | 0o111)
    except OSError:
        pass
    _log(log, "Wrote diagnose-frame.sh")
    return diag


def write_steam_helpers(game_dir: Path, game_name: str, version: str, launcher: Path, log: Optional[LogFn] = None) -> None:
    launcher_base = launcher.name

    # Quiet attribution + conversion metadata. This lives in a hidden-ish
    # project directory so normal players never see it, while anyone inspecting
    # a converted build can tell where the ARM64 port came from.
    metadata_dir = game_dir / ".renframe"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "conversion.txt").write_text(
        "Converted to Linux ARM64 with RenFrame.\n"
        "RenFrame by Zum Glitchbrain.\n"
        f"Runtime: Ren'Py {version}\n",
        encoding="utf-8",
        newline="\n",
    )

    wrap = game_dir / "launch-steam.sh"
    wrap.write_text(
        f"""#!/usr/bin/env bash
# Converted to Linux ARM64 with RenFrame.
# RenFrame by Zum Glitchbrain.
# Steam-friendly wrapper. The stock Ren'Py launcher resolves its own basedir,
# so only forward the caller's real arguments.
set -euo pipefail
GAME_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$GAME_DIR"

# Steam Frame's nested desktop/Xwayland session lives under frametop. Steam
# shortcuts do not reliably inherit the variables needed to reach it, so
# discover the live session at launch time. The xauth filename changes between
# sessions and must never be hardcoded.
FRAME_RUNTIME_DIR="/run/user/$(id -u)/frametop"
if [[ -d "$FRAME_RUNTIME_DIR" ]]; then
    export XDG_RUNTIME_DIR="$FRAME_RUNTIME_DIR"
    export DISPLAY=":2"
    export SDL_VIDEODRIVER="x11"

    XAUTH_FILE=""
    for candidate in "$FRAME_RUNTIME_DIR"/xauth_*; do
        [[ -r "$candidate" ]] || continue
        if [[ -z "$XAUTH_FILE" || "$candidate" -nt "$XAUTH_FILE" ]]; then
            XAUTH_FILE="$candidate"
        fi
    done
    if [[ -n "$XAUTH_FILE" ]]; then
        export XAUTHORITY="$XAUTH_FILE"
    else
        printf 'WARNING: no readable xauth_* file found in %s; X11 launch may fail.\n' \
            "$FRAME_RUNTIME_DIR" >&2
    fi
fi

# Windows-created ZIPs may lose Unix executable bits on both the Ren'Py
# launcher script and the ARM runtime binaries.
chmod +x "$GAME_DIR/{launcher_base}" 2>/dev/null || true
for runtime in \
    "$GAME_DIR"/lib/*-linux-aarch64/renpy \
    "$GAME_DIR"/lib/*-linux-aarch64/python \
    "$GAME_DIR"/lib/*-linux-aarch64/{game_name}; do
    [[ -f "$runtime" ]] && chmod +x "$runtime" 2>/dev/null || true
done

exec "$GAME_DIR/{launcher_base}" "$@"
""",
        encoding="utf-8",
        newline="\n",
    )

    diag = write_frame_diagnostics(game_dir, game_name, log=log)
    add = game_dir / "add-to-steam.sh"
    add.write_text(
        r'''#!/usr/bin/env bash
# Register this Ren'Py Linux ARM build as a non-Steam game.
# Run on the ARM device AFTER unpacking (Steam must be running).
set -euo pipefail

GAME_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$GAME_DIR"

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

LAUNCH=""
if [[ -x "$GAME_DIR/launch-steam.sh" ]]; then
  LAUNCH="$GAME_DIR/launch-steam.sh"
else
  for f in "$GAME_DIR"/*.sh; do
    [[ -e "$f" ]] || continue
    base=$(basename "$f")
    case "$base" in
      make-linux-arm.sh|add-to-steam.sh|launch-steam.sh|diagnose-frame.sh) continue ;;
    esac
    if grep -q 'RENPY_PLATFORM' "$f" 2>/dev/null; then
      LAUNCH="$f"
      break
    fi
  done
fi
[[ -n "$LAUNCH" ]] || die "No launch-steam.sh or Ren'Py .sh launcher found in $GAME_DIR"
LAUNCH=$(readlink -f "$LAUNCH" 2>/dev/null || realpath "$LAUNCH" 2>/dev/null || echo "$LAUNCH")

GAME_NAME=$(basename "$LAUNCH" .sh)
[[ "$GAME_NAME" == "launch-steam" ]] && GAME_NAME=$(basename "$GAME_DIR")

DESKTOP="$GAME_DIR/${GAME_NAME}.desktop"
if [[ ! -f "$DESKTOP" ]]; then
  for d in "$GAME_DIR"/*.desktop; do
    [[ -e "$d" ]] || continue
    DESKTOP="$d"
    break
  done
fi

NAME="$GAME_NAME"
if [[ -f "$DESKTOP" ]]; then
  old_name=$(grep -E '^Name=' "$DESKTOP" | head -1 | cut -d= -f2- || true)
  [[ -n "$old_name" ]] && NAME="$old_name"
fi
cat > "$DESKTOP" <<EOD
[Desktop Entry]
Name=$NAME
Comment=$NAME (native Linux ARM Ren'Py)
Exec=$LAUNCH
Path=$GAME_DIR
Icon=applications-games
Terminal=false
Type=Application
Categories=Game;
StartupNotify=false
EOD
chmod +x "$DESKTOP" 2>/dev/null || true
DESKTOP=$(readlink -f "$DESKTOP" 2>/dev/null || realpath "$DESKTOP" 2>/dev/null || echo "$DESKTOP")
log "Desktop entry: $DESKTOP"
log "Launch target: $LAUNCH"

steam_is_running() {
  pgrep -x steam >/dev/null 2>&1 \
    || pgrep -f '[/]steamrt.*/steam' >/dev/null 2>&1 \
    || pgrep -f '[.]local/share/Steam/.*/steam$' >/dev/null 2>&1
}

if command -v steamos-add-to-steam >/dev/null 2>&1; then
  log "Adding launcher directly via steamos-add-to-steam…"
  # SteamVR on Steam Frame does not reliably follow .desktop indirection.
  # Register the executable wrapper itself, which is known to launch correctly
  # from both the desktop and SteamVR library.
  steamos-add-to-steam "$LAUNCH"
  log "Done. Check your Steam library for \"$NAME\"."
  log "Properties → Compatibility: Steam Linux Runtime / native (not Proton)."
  exit 0
fi

command -v steam >/dev/null 2>&1 || die "Neither steamos-add-to-steam nor steam found.
Add manually: Steam → Add a Non-Steam Game → $LAUNCH"

steam_is_running || die "Steam does not appear to be running. Start Steam, then re-run:
  $0"

py=$(command -v python3 || command -v python || true)
if [[ -n "$py" ]]; then
  encoded=$("$py" -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$LAUNCH")
else
  encoded=${LAUNCH// /%20}
fi

touch /tmp/addnonsteamgamefile 2>/dev/null || true
log "Adding launcher directly via steam://addnonsteamgame/…"
steam "steam://addnonsteamgame/${encoded}"
log "Done. Check your Steam library for \"$NAME\"."
log "Properties → Compatibility: Steam Linux Runtime / native (not Proton)."
''',
        encoding="utf-8",
        newline="\n",
    )

    desk = game_dir / f"{game_name}.desktop"
    desk.write_text(
        f"""[Desktop Entry]
Name={game_name}
Comment={game_name} (native Linux ARM / Ren'Py {version})
Exec={game_dir.as_posix()}/launch-steam.sh
Path={game_dir.as_posix()}
Icon=applications-games
Terminal=false
Type=Application
Categories=Game;
StartupNotify=false
""",
        encoding="utf-8",
        newline="\n",
    )

    readme = game_dir / "README for adding games to steam.txt"
    readme.write_text(
        f"""================================================================================
  README — Adding this game to Steam (Linux ARM / Steam Frame)
================================================================================

This folder is a Ren'Py game already patched to run natively on Linux ARM64
(aarch64). You do NOT need to run the converter again on this device.

WHAT TO DO (on the Frame / ARM machine)
---------------------------------------
1. Make sure Steam is running (Big Picture / Game Mode / Desktop — any is fine).

2. Open a terminal in THIS folder (the one that contains add-to-steam.sh).

3. Run:

     chmod +x add-to-steam.sh launch-steam.sh diagnose-frame.sh *.sh
     ./add-to-steam.sh

4. Open your Steam library and look for "{game_name}" (non-Steam shortcut).

5. Optional but recommended — game Properties → Compatibility:
     use "Steam Linux Runtime" or force native Linux
     do NOT use Proton for this build


IF SOMETHING GOES WRONG
-----------------------
- "Steam does not appear to be running"
    Start Steam, then run ./add-to-steam.sh again.

- Game appears but won't launch
    Check Compatibility (native / Steam Linux Runtime, not Proton).
    Or try from a terminal:

      ./launch-steam.sh

    For a full launch trace:

      ./diagnose-frame.sh --launch

- You would rather add it by hand
    Steam → Games → Add a Non-Steam Game to My Library
    Browse to:  launch-steam.sh   (or the .desktop file in this folder)


FILES IN THIS FOLDER (Steam-related)
------------------------------------
  add-to-steam.sh     ← run this on the Frame to register with Steam
  launch-steam.sh     ← what Steam should launch
  diagnose-frame.sh   ← platform/runtime checks + traced launch
  {game_name}.desktop
  README for adding games to steam.txt  ← this file


PLAY WITHOUT STEAM
------------------
  ./{launcher_base}
  or
  ./launch-steam.sh

================================================================================
""",
        encoding="utf-8",
        newline="\n",
    )

    for p in (wrap, add):
        try:
            p.chmod(p.stat().st_mode | 0o111)
        except OSError:
            pass
    _log(log, "Wrote launch-steam.sh, add-to-steam.sh, desktop, Steam README")


def create_zip_archive(
    game_dir: Path,
    game_name: str,
    out_path: Path,
    full: bool = False,
    log: Optional[LogFn] = None,
    progress: Optional[ProgressFn] = None,
) -> Path:
    skip_dirs = {".renpy-arm-cache", "_arm_experiment", ".git"}
    skip_names = {
        f"{game_name}-linux-aarch64.zip",
        f"{game_name}-linux-aarch64.7z",
        f"{game_name}-linux-aarch64.tar.gz",
        out_path.name,
    }

    def wanted(p: Path) -> bool:
        rel = p.relative_to(game_dir)
        parts = rel.parts
        if parts and parts[0] in skip_dirs:
            return False
        if rel.name in skip_names:
            return False
        if str(rel).endswith(".bak-before-arm"):
            return False
        if not full:
            if len(parts) > 1 and parts[0] == "lib" and parts[1].startswith(("py3-windows-", "py2-windows-")):
                return False
            if parts[:1] == ("lib",) and len(parts) > 1 and "linux-x86_64" in parts[1]:
                return False
            if rel.suffix.lower() == ".exe":
                return False
        return True

    files = [
        path for path in game_dir.rglob("*")
        if path.is_file() and wanted(path)
    ]
    total_bytes = sum(path.stat().st_size for path in files)
    written_bytes = 0

    if out_path.exists():
        out_path.unlink()
    _log(log, f"Creating archive {out_path.name}…")
    _progress(progress, "Creating output zip", 0.0, out_path.name)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            arc = Path(game_name) / path.relative_to(game_dir)
            arcname = str(arc).replace("\\", "/")
            info = zipfile.ZipInfo.from_file(path, arcname=arcname)
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 6
            file_size = path.stat().st_size
            with path.open("rb") as source_file, zf.open(info, "w", force_zip64=True) as zip_file:
                while True:
                    chunk = source_file.read(1024 * 1024)
                    if not chunk:
                        break
                    zip_file.write(chunk)
                    written_bytes += len(chunk)
                    fraction = written_bytes / total_bytes if total_bytes else 1.0
                    _progress(
                        progress,
                        "Creating output zip",
                        fraction,
                        f"{path.name}  ·  {_human_bytes(written_bytes)} / {_human_bytes(total_bytes)}",
                    )
            if file_size == 0 and total_bytes == 0:
                _progress(progress, "Creating output zip", 1.0, path.name)
    _progress(progress, "Creating output zip", 1.0, out_path.name)
    _log(log, f"Archive ready: {out_path}")
    return out_path


FRAME_INSTRUCTIONS = """On your Steam Frame (after copying the zip):

1. Unpack the zip somewhere convenient (e.g. ~/Games/).
2. Start Steam.
3. In a terminal inside the unpacked game folder:

     chmod +x add-to-steam.sh launch-steam.sh diagnose-frame.sh *.sh
     ./add-to-steam.sh

4. Find the game in your Steam library (non-Steam shortcut).
5. Properties → Compatibility: Steam Linux Runtime / native — not Proton.

Play without Steam: ./launch-steam.sh
"""


def convert_game(
    source: Path,
    *,
    output_zip: Optional[Path] = None,
    version_override: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    force: bool = False,
    work_dir: Optional[Path] = None,
    full_archive: bool = False,
    log: Optional[LogFn] = None,
    progress: Optional[ProgressFn] = None,
) -> ConvertResult:
    """
    Convert a Ren'Py PC game folder or archive into a Linux aarch64 zip.

    By default the game is patched in a working copy under work_dir when the
    source is an archive; folders are patched in place then zipped beside them.
    """
    messages: list[str] = []

    def emit(msg: str) -> None:
        messages.append(msg)
        _log(log, msg)

    work = work_dir or Path(tempfile.mkdtemp(prefix="renpy-arm-work-"))
    work.mkdir(parents=True, exist_ok=True)
    cache = cache_dir or default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)

    _progress(progress, "Inspecting game", None, source.name)
    game_dir = resolve_input(source, work, log=emit)

    profile_match = detect_profile(game_dir)
    if profile_match is not None:
        _progress(progress, "Applying compatibility profile", None, profile_match.profile.title)
        try:
            game_dir = migrate_profile(
                profile_match,
                game_dir,
                work_root=work,
                cache_dir=cache,
                force=force,
                log=emit,
            )
        except ProfileError as exc:
            raise ConvertError(str(exc)) from exc

    if not is_modern_renpy_game(game_dir):
        legacy_version = detect_legacy_version(game_dir)
        if legacy_version:
            raise ConvertError(
                f"Legacy Ren'Py {legacy_version} detected, but RenFrame has no "
                "compatibility profile for this game yet."
            )
        raise ConvertError(
            "Ren'Py game detected, but this distribution does not contain the "
            "modern lib/ runtime layout and no compatibility profile matched."
        )

    _progress(progress, "Detecting Ren'Py version", None, None)
    launcher = find_launcher_sh(game_dir)
    game_name = launcher.stem
    version = resolve_conversion_version(
        game_dir,
        version_override=version_override,
        profile_match=profile_match,
    )
    python_tag = detect_python_tag(game_dir, version)
    if profile_match is not None and not version_override:
        emit(f"Compatibility profile pins Ren'Py {version}")
    emit(f"Game: {game_name}")
    emit(f"Ren'Py {version} ({python_tag})")

    dest = game_dir / "lib" / f"{python_tag}-linux-aarch64"
    need_extract = force or not (dest / "librenpython.so").is_file()
    runtime_version = version
    if need_extract:
        sdk, runtime_version = download_sdk(
            version,
            cache,
            force=force,
            log=emit,
            progress=progress,
        )
        _progress(progress, "Verifying runtime", None, sdk.name)
        verify_sdk_checksum(sdk, runtime_version, log=emit)
        _progress(progress, "Extracting ARM64 runtime", None, sdk.name)
        extract_aarch64(sdk, game_dir, python_tag, game_name, log=emit)
        if runtime_version != version:
            _progress(
                progress,
                "Synchronizing Ren'Py engine",
                None,
                f"{version} → {runtime_version}",
            )
            sync_engine_from_sdk(
                sdk,
                game_dir,
                source_version=version,
                runtime_version=runtime_version,
                log=emit,
            )
            sync_runtime_support_from_sdk(
                sdk,
                game_dir,
                python_tag=python_tag,
                runtime_version=runtime_version,
                log=emit,
            )
    else:
        emit(f"Already have {dest.name} (use force to re-download)")
        named = dest / game_name
        renpy_bin = dest / "renpy"
        if renpy_bin.is_file() and not named.exists():
            shutil.copy2(renpy_bin, named)

    _progress(progress, "Patching launchers", None, launcher.name)
    patch_launcher_sh(launcher, python_tag=python_tag, log=emit)
    write_steam_helpers(game_dir, game_name, runtime_version, launcher, log=emit)

    if output_zip is None:
        output_zip = game_dir.parent / f"{game_name}-linux-aarch64.zip"
    output_zip = output_zip.resolve()
    create_zip_archive(
        game_dir,
        game_name,
        output_zip,
        full=full_archive,
        log=emit,
        progress=progress,
    )

    _progress(progress, "Done", 1.0, output_zip.name)
    emit("Done.")
    return ConvertResult(
        game_dir=game_dir,
        game_name=game_name,
        version=version,
        archive_path=output_zip,
        messages=messages,
    )
