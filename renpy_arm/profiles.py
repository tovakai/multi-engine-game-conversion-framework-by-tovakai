"""Known compatibility profiles for legacy Ren'Py games.

Profiles are deliberately isolated from the generic runtime-transplant path.  A
profile may normalize a known legacy title into a modern Ren'Py distribution;
the normal converter then takes over and installs the ARM64 runtime.
"""
from __future__ import annotations

import re
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

LogFn = Callable[[str], None]


class ProfileError(Exception):
    """A compatibility profile could not complete its migration."""


@dataclass(frozen=True)
class CompatibilityProfile:
    id: str
    title: str
    target_version: str
    reference_url: str
    experimental: bool = True


@dataclass(frozen=True)
class ProfileMatch:
    profile: CompatibilityProfile
    variant: str


KATAWA_PROFILE = CompatibilityProfile(
    id="katawa-shoujo-legacy",
    title="Katawa Shoujo (legacy Ren'Py 6.x)",
    target_version="8.0.3",
    reference_url="https://github.com/gcammisa/KatawaShoujo-RenPy8",
)

# Pin upstream inputs so a future upstream change cannot silently change a
# RenFrame conversion recipe.
KATAWA_MODERN_RELEASE_URL = (
    "https://github.com/gcammisa/KatawaShoujo-RenPy8/releases/download/"
    "8.0.3/katawashoujo-linux.tar.bz2"
)
KATAWA_MODERN_RELEASE_NAME = "katawashoujo-renpy8-8.0.3-linux.tar.bz2"

KATAWA_HD_REPO = "scoopgoop/Katawa-Shoujo-HD-Upscale"
KATAWA_HD_COMMIT = "ef24235c4ae6f9c67e371cfd79446cff2c02f3f8"
KATAWA_HD_RAW = (
    "https://raw.githubusercontent.com/"
    f"{KATAWA_HD_REPO}/{KATAWA_HD_COMMIT}/"
)

# These are the game scripts present as source in the HD project.  The rest of
# the legacy release is represented by compiled .rpyc; the known-good Ren'Py 8
# port supplies modern versions of those files.
KATAWA_HD_SOURCE_FILES = (
    "game/script-a1-sunday.rpy",
    "game/script-a1-thursday.rpy",
    "game/script-a2-hanako.rpy",
    "game/script-a2-shizune.rpy",
    "game/script-a3-hanako.rpy",
    "game/ui-strings.rpy",
    "game/ui_code.rpy",
    "game/ui_i18n.rpy",
    "game/ui_ingamemenu.rpy",
    "game/ui_labels.rpy",
    "game/ui_settings.rpy",
)


# The packaged HD repository keeps its 1080p UI as loose files. The legacy
# release the user supplies may not contain those files or .rpa archives, so
# cache and overlay the pinned UI payload explicitly. This is ~19 MB at the
# pinned commit, much smaller than cloning the multi-gigabyte HD repository.
KATAWA_HD_UI_FILES = (
    "game/ui/4lsl-small.png",
    "game/ui/bg-acttitleframe.png",
    "game/ui/bg-choice.png",
    "game/ui/bg-choice_nochoice.png",
    "game/ui/bg-comment.png",
    "game/ui/bg-config.png",
    "game/ui/bg-doublespeak.png",
    "game/ui/bg-doublespeak_old.png",
    "game/ui/bg-ex-gallery-lockedimage.png",
    "game/ui/bg-gm.png",
    "game/ui/bg-lockedtrack.png",
    "game/ui/bg-narration.png",
    "game/ui/bg-note.png",
    "game/ui/bg-nvl.png",
    "game/ui/bg-nvl_old.png",
    "game/ui/bg-popup.png",
    "game/ui/bg-say.png",
    "game/ui/bt-blank.png",
    "game/ui/bt-cf-bar-left.png",
    "game/ui/bt-cf-bar-right.png",
    "game/ui/bt-cf-checked.png",
    "game/ui/bt-cf-thumb.png",
    "game/ui/bt-cf-unchecked.png",
    "game/ui/bt-cg-locked.png",
    "game/ui/bt-del.png",
    "game/ui/bt-gamepad.png",
    "game/ui/bt-language.png",
    "game/ui/bt-logolarge-heartonly.png",
    "game/ui/bt-logolarge.png",
    "game/ui/bt-logoonly.png",
    "game/ui/bt-musicplay.png",
    "game/ui/bt-musicstop.png",
    "game/ui/bt-return.png",
    "game/ui/bt-scribble.png",
    "game/ui/bt-star.png",
    "game/ui/bt-vscrollbar.png",
    "game/ui/bt-vscrollbar2.png",
    "game/ui/bt-vscrolldown.png",
    "game/ui/bt-vscrollthumb.png",
    "game/ui/bt-vscrollup.png",
    "game/ui/cantaloupes.jpg",
    "game/ui/cantaloupes.png",
    "game/ui/climatic.jpg",
    "game/ui/cred_logo.png",
    "game/ui/ctc.png",
    "game/ui/ctc_strip.png",
    "game/ui/cuddlefish.jpg",
    "game/ui/cuddlefish.png",
    "game/ui/flourish_center.png",
    "game/ui/flourish_left.png",
    "game/ui/flourish_right.png",
    "game/ui/icon.png",
    "game/ui/main/00_tc1-hisao.png",
    "game/ui/main/01_tc2-hanako.png",
    "game/ui/main/02_tc3-hanako.png",
    "game/ui/main/03_tc2-emi.png",
    "game/ui/main/04_tc3-emi.png",
    "game/ui/main/05_tc4-emi.png",
    "game/ui/main/06_tc4-hanako.png",
    "game/ui/main/07_tc2-lilly.png",
    "game/ui/main/08_tc3-lilly.png",
    "game/ui/main/09_tc4-lilly.png",
    "game/ui/main/10_tc2-rin.png",
    "game/ui/main/11_tc3-rin-hisao.png",
    "game/ui/main/12_tc3-rin-rin.png",
    "game/ui/main/13_tc4-rin.png",
    "game/ui/main/14_tc2-shizune.png",
    "game/ui/main/15_tc3-shizune.png",
    "game/ui/main/16_tc4-shizune.png",
    "game/ui/main/bg-main.png",
    "game/ui/mousecursor.png",
    "game/ui/prawns.png",
    "game/ui/roll_mask.png",
    "game/ui/sd-auto.png",
    "game/ui/sd-emi-c.png",
    "game/ui/sd-emi.png",
    "game/ui/sd-hanako-c.png",
    "game/ui/sd-hanako.png",
    "game/ui/sd-lilly-c.png",
    "game/ui/sd-lilly.png",
    "game/ui/sd-mute.png",
    "game/ui/sd-rin-c.png",
    "game/ui/sd-rin.png",
    "game/ui/sd-shizune-c.png",
    "game/ui/sd-shizune.png",
    "game/ui/sd-skip.png",
    "game/ui/tc-neutral.png",
    "game/ui/tr-checkwipe.png",
    "game/ui/tr-checkwipe2.png",
    "game/ui/tr-clockwipe.png",
    "game/ui/tr-dots_col.png",
    "game/ui/tr-flashback.png",
    "game/ui/tr-letter.png",
)

# Asset directories are safe to take from the user's copy.  Do not copy the
# legacy engine, common/, bytecode caches, or compiled scripts into the modern
# base.
KATAWA_ASSET_DIRS = (
    "bgm",
    "bgs",
    "event",
    "font",
    "sfx",
    "sprites",
    "ui",
    "vfx",
    "video",
)
KATAWA_ASSET_FILES = (
    "presplash.png",
)


def _log(log: Optional[LogFn], message: str) -> None:
    if log:
        log(message)


def detect_legacy_version(game_dir: Path) -> Optional[str]:
    """Return the raw legacy Ren'Py version string when it can be read."""
    init_py = game_dir / "renpy" / "__init__.py"
    if not init_py.is_file():
        return None
    try:
        text = init_py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(
        r"""(?m)^\s*version\s*=\s*["']Ren['’]?Py\s+([^"']+)["']""",
        text,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r"""(?m)^\s*version\s*=\s*["']([^"']+)["']""",
        text,
    )
    return match.group(1).strip() if match else None


def is_legacy_renpy_game(game_dir: Path) -> bool:
    """Recognize pre-modern distributions that do not have lib/."""
    if not (game_dir / "game").is_dir() or not (game_dir / "renpy").is_dir():
        return False
    markers = (
        game_dir / "renpy.code",
        game_dir / "python25.dll",
        game_dir / "python26.dll",
        game_dir / "python27.dll",
    )
    return any(p.exists() for p in markers) or detect_legacy_version(game_dir) is not None


def _looks_like_katawa(game_dir: Path) -> bool:
    version = detect_legacy_version(game_dir)
    if not version or not version.startswith("6.10.2"):
        return False

    required = (
        game_dir / "python25.dll",
        game_dir / "renpy.code",
        game_dir / "game" / "imachine.rpyc",
        game_dir / "game" / "ui_settings.rpyc",
    )
    if not all(p.exists() for p in required):
        return False

    # A second distinctive route file makes accidental matching of another
    # Ren'Py 6.10.2 title very unlikely without depending on the folder name.
    route_markers = (
        game_dir / "game" / "script-a1-monday.rpyc",
        game_dir / "game" / "script-a1-sunday.rpyc",
    )
    return any(p.exists() for p in route_markers)


def _png_dimensions(path: Path) -> Optional[tuple[int, int]]:
    """Read a PNG IHDR without needing Pillow."""
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def _katawa_variant(game_dir: Path) -> str:
    if "hd" in game_dir.name.lower():
        return "hd"

    dims = _png_dimensions(game_dir / "game" / "presplash.png")
    if dims and (dims[0] >= 1200 or dims[1] >= 900):
        return "hd"

    # The HD project does not consistently ship a presplash, and users often
    # rename the extracted folder. Detect the actual HD source/layout instead
    # of relying on packaging names.
    ui_settings = game_dir / "game" / "ui_settings.rpy"
    if ui_settings.is_file():
        try:
            text = ui_settings.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        hd_markers = (
            "style.default.size = 41",
            "LiveComposite((1440, 1080)",
            "ui.vbox(xpos = 324, ypos = 216)",
        )
        if any(marker in text for marker in hd_markers):
            return "hd"

    say_dims = _png_dimensions(game_dir / "game" / "ui" / "bg-say.png")
    if say_dims and say_dims[0] >= 1200:
        return "hd"

    return "vanilla"


def detect_profile(game_dir: Path) -> Optional[ProfileMatch]:
    if _looks_like_katawa(game_dir):
        return ProfileMatch(KATAWA_PROFILE, _katawa_variant(game_dir))
    return None


def _download(
    url: str,
    destination: Path,
    *,
    force: bool = False,
    log: Optional[LogFn] = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and not force:
        _log(log, f"Using cached compatibility asset: {destination.name}")
        return destination

    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        partial.unlink()

    _log(log, f"Downloading compatibility asset: {url}")
    try:
        urllib.request.urlretrieve(url, partial)
    except Exception as exc:
        try:
            partial.unlink()
        except OSError:
            pass
        raise ProfileError(f"Failed to download compatibility asset.\n{url}\n{exc}") from exc

    partial.replace(destination)
    return destination


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    """Extract a tar archive without allowing path/link traversal."""
    destination = destination.resolve()
    with tarfile.open(archive, "r:*") as tf:
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
                raise ProfileError(
                    f"Unsafe path in compatibility archive: {member.name}"
                ) from exc
        tf.extractall(destination)


def _find_modern_game(root: Path) -> Path:
    candidates = [root]
    candidates.extend(p for p in root.iterdir() if p.is_dir())
    for parent in list(candidates[1:]):
        try:
            candidates.extend(p for p in parent.iterdir() if p.is_dir())
        except OSError:
            pass

    for candidate in candidates:
        if (
            (candidate / "game").is_dir()
            and (candidate / "renpy").is_dir()
            and (candidate / "lib").is_dir()
            and any(candidate.glob("*.sh"))
        ):
            return candidate
    raise ProfileError("Downloaded Katawa compatibility base did not contain a Ren'Py game.")


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _overlay_user_katawa_assets(source_game: Path, modern_game: Path, log: Optional[LogFn]) -> None:
    source_payload = source_game / "game"
    target_payload = modern_game / "game"

    copied = 0
    for name in KATAWA_ASSET_DIRS:
        src = source_payload / name
        if not src.is_dir():
            continue
        _replace_tree(src, target_payload / name)
        copied += 1

    for name in KATAWA_ASSET_FILES:
        src = source_payload / name
        if src.is_file():
            shutil.copy2(src, target_payload / name)
            copied += 1

    _log(log, f"Reapplied user-owned Katawa assets ({copied} asset groups/files)")


def _overlay_user_katawa_archives(
    source_game: Path,
    modern_game: Path,
    log: Optional[LogFn],
) -> int:
    """Copy legacy Katawa resource archives into the normalized game.

    The packaged HD release keeps most of its upscaled assets in .rpa files
    instead of loose game/ui, game/event, etc. Ren'Py 8 still understands the
    legacy RPA formats. Prefix copied archives with "zz-" so they sort ahead
    of the modern port's data.rpa and therefore win for matching resource paths.

    Loose modernized .rpy/.rpyc files still take precedence over archive
    contents, so script fixes remain authoritative.
    """
    target_payload = modern_game / "game"
    target_payload.mkdir(parents=True, exist_ok=True)

    # Normal Ren'Py distributions keep archives under game/, but some legacy
    # repacks place them beside the launcher or one level above an auto-descended
    # game directory. Accept those wrapper layouts without scanning arbitrary
    # parent directories.
    payloads = [source_game / "game", source_game]

    parent = source_game.parent
    try:
        sibling_dirs = [
            p for p in parent.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ]
    except OSError:
        sibling_dirs = []
    if len(sibling_dirs) == 1 and sibling_dirs[0] == source_game:
        payloads.extend((parent / "game", parent))

    archive_sources = {}
    for payload in payloads:
        if not payload.is_dir():
            continue
        for src in payload.glob("*.rpa"):
            archive_sources.setdefault(src.name, src)

    copied = 0
    for src in sorted(archive_sources.values(), key=lambda p: p.name.lower()):
        try:
            with src.open("rb") as fh:
                header = fh.read(8)
        except OSError:
            continue
        if not header.startswith(b"RPA-"):
            _log(log, f"Skipping unrecognized archive: {src.name}")
            continue

        dest = target_payload / f"zz-renframe-hd-{src.name}"
        shutil.copy2(src, dest)
        copied += 1

    if copied:
        _log(log, f"Reapplied {copied} user-owned Katawa resource archives")
    else:
        _log(log, "No local Katawa .rpa resource archives found to reapply")
    return copied


def _modernize_katawa_hd_source(text: str) -> str:
    """Apply the small Python 2 -> 3 syntax fixes required by the pinned HD sources.

    Keep this deliberately narrow. The Ren'Py 8 community port already carries
    compatibility shims for runtime-era names such as xrange/unicode; these
    replacements only address syntax that Python 3 cannot parse at all.
    """
    text = text.replace("except Exception, e:", "except Exception as e:")
    text = text.replace(
        'print "JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN"',
        'print("JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN")',
    )
    # Python 2 exposed the old sets module. Python 3's built-in set type is
    # the direct replacement, and the known-good Ren'Py 8 port makes the same
    # migration in ui_ingamemenu.rpy.
    text = re.sub(r"(?m)^([ \t]*)import sets[ \t]*\n", "", text)
    text = text.replace("sets.Set()", "set()")

    # Ren'Py 8's Render constructor no longer accepts the legacy opaque=
    # keyword. The known-good Ren'Py 8 Katawa port drops it as well.
    text = text.replace(
        "renpy.display.render.Render(width, height, opaque=True)",
        "renpy.display.render.Render(width, height)",
    )

    # Ren'Py 8 collapses the HD release's whitespace-only narrator name. That
    # removes the invisible name row and shifts narration text upward while
    # named dialogue remains aligned. The known-good Ren'Py 8 port uses an
    # invisible non-whitespace marker to preserve the row height.
    text = text.replace(
        "store.narrator = Character(' ', what_prefix=\"\", what_suffix=\"\", show_function=say_wrapper)",
        "store.narrator = Character(NARRATOR_NAME, what_prefix=\"\", what_suffix=\"\", show_function=say_wrapper)",
    )
    text = text.replace(
        "    init_vars()\n    _game_menu_screen = \"gm_bare\"",
        "    init_vars()\n    NARRATOR_NAME = \"{color=#0000}#{/color} \"\n    _game_menu_screen = \"gm_bare\"",
    )
    text = text.replace(
        "        if not who:\n            who = \"\"",
        "        if not who or who == NARRATOR_NAME or who == preparse_say_for_store(NARRATOR_NAME):\n            who = \"\"",
    )

    # Ren'Py 8 no longer exposes Context.main_menu. The community Ren'Py 8
    # port always uses the compatibility flag stored in _main_menu.
    text = text.replace(
        "    def mm_context():\n        if is_glrenpy():\n            return renpy.context()._main_menu\n        else:\n            return renpy.context().main_menu",
        "    def mm_context():\n        return renpy.context()._main_menu",
    )

    # The modern port explicitly asks Ren'Py 8 to preserve 6.10.2-era script
    # semantics. The HD source override otherwise drops this setting.
    if "config.script_version = (6,10,2)" not in text:
        text = text.replace(
            "    config.minimumvolume = -10.0",
            "    config.minimumvolume = -10.0\n    config.script_version = (6,10,2)",
        )

    # Python 3 dict views replace the old iteritems() API.
    text = text.replace(".iteritems()", ".items()")
    return text


def _overlay_hd_ui_assets(
    modern_game: Path,
    cache_dir: Path,
    *,
    force: bool,
    log: Optional[LogFn],
) -> int:
    """Overlay the pinned 1080p Katawa HD UI payload onto the modern base."""
    source_cache = cache_dir / "katawa-hd-ui" / KATAWA_HD_COMMIT
    copied = 0

    _log(log, "Applying Katawa Shoujo HD UI assets…")
    for relative in KATAWA_HD_UI_FILES:
        cached = source_cache / relative
        _download(
            KATAWA_HD_RAW + relative,
            cached,
            force=force,
            log=log,
        )

        destination = modern_game / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, destination)
        copied += 1

    _log(log, f"Applied {copied} pinned HD UI assets")
    return copied


def _overlay_hd_sources(
    modern_game: Path,
    cache_dir: Path,
    *,
    force: bool,
    log: Optional[LogFn],
) -> None:
    source_cache = cache_dir / "katawa-hd-source" / KATAWA_HD_COMMIT

    _log(log, "Applying Katawa Shoujo HD source overrides…")
    for relative in KATAWA_HD_SOURCE_FILES:
        cached = source_cache / relative
        _download(
            KATAWA_HD_RAW + relative,
            cached,
            force=force,
            log=log,
        )

        destination = modern_game / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        text = cached.read_text(encoding="utf-8", errors="replace")
        modernized = _modernize_katawa_hd_source(text)
        destination.write_text(modernized, encoding="utf-8", newline="\n")

        compiled = destination.with_suffix(".rpyc")
        if compiled.exists():
            compiled.unlink()

    # Force Ren'Py to rebuild caches against the overlaid HD source.
    game_cache = modern_game / "game" / "cache"
    if game_cache.exists():
        shutil.rmtree(game_cache)

    _log(
        log,
        f"Applied {len(KATAWA_HD_SOURCE_FILES)} HD source overrides "
        "(including Python 3 syntax fixes)",
    )


def migrate_profile(
    match: ProfileMatch,
    source_game: Path,
    *,
    work_root: Path,
    cache_dir: Path,
    force: bool = False,
    log: Optional[LogFn] = None,
) -> Path:
    """Normalize a known legacy game into a modern distribution."""
    if match.profile.id != KATAWA_PROFILE.id:
        raise ProfileError(f"No migrator implemented for profile: {match.profile.id}")

    _log(log, f"Known compatibility profile: {match.profile.title}")
    _log(log, f"Detected variant: {match.variant}")
    _log(log, f"Migration target: Ren'Py {match.profile.target_version}")

    archive = _download(
        KATAWA_MODERN_RELEASE_URL,
        cache_dir / KATAWA_MODERN_RELEASE_NAME,
        force=force,
        log=log,
    )

    extract_root = work_root / "compat-katawa-modern"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)

    _log(log, "Extracting known-good Ren'Py 8 Katawa base…")
    _safe_extract_tar(archive, extract_root)
    modern_game = _find_modern_game(extract_root)

    _overlay_user_katawa_assets(source_game, modern_game, log)

    hd_archive_count = 0
    hd_ui_count = 0
    if match.variant == "hd":
        hd_archive_count = _overlay_user_katawa_archives(source_game, modern_game, log)
        hd_ui_count = _overlay_hd_ui_assets(
            modern_game,
            cache_dir,
            force=force,
            log=log,
        )
        _overlay_hd_sources(
            modern_game,
            cache_dir,
            force=force,
            log=log,
        )

    note = modern_game / "RENFRAME-COMPATIBILITY.txt"
    note.write_text(
        (
            "RenFrame legacy compatibility migration\n"
            "=======================================\n\n"
            f"Profile: {match.profile.id}\n"
            f"Variant: {match.variant}\n"
            f"Target Ren'Py: {match.profile.target_version}\n\n"
            "This build was normalized using the known Ren'Py 8 Katawa Shoujo port:\n"
            f"{match.profile.reference_url}\n"
            "Pinned release: 8.0.3\n\n"
            "For the HD variant, RenFrame reapplies the user's local .rpa resource "
            "archives with high load priority, then reapplies source overrides from:\n"
            f"HD resource archives reapplied: {hd_archive_count}\n"
            f"Pinned HD UI assets applied: {hd_ui_count}\n"
            f"https://github.com/{KATAWA_HD_REPO}\n"
            f"Pinned commit: {KATAWA_HD_COMMIT}\n\n"
            "The user's local game copy supplies the game assets that are overlaid "
            "onto the modern compatibility base before ARM64 conversion.\n"
        ),
        encoding="utf-8",
        newline="\n",
    )

    _log(log, "Legacy Katawa normalized; continuing through normal ARM64 conversion")
    return modern_game
