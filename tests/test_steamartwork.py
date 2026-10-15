"""Exercise real shortcut bytes and artwork files without touching live Steam."""
import json
from pathlib import Path
import struct

import pytest
from PIL import Image

from steamartwork import backend as art


def vdf_entry(appid=0xF1234567, name="A game", exe='"/games/play.sh"'):
    def string(key, value):
        return b"\x01" + key.encode() + b"\0" + value.encode() + b"\0"
    return (b"\x00shortcuts\0\x000\0\x02appid\0" + struct.pack("<I", appid)
            + string("AppName", name) + string("Exe", exe)
            + b"\x00tags\0" + string("0", "Favorites") + b"\x08\x08\x08\x08")


@pytest.fixture
def profile(tmp_path):
    profile = tmp_path / "Steam/userdata/123"
    (profile / "config/grid").mkdir(parents=True)
    (profile / "config/shortcuts.vdf").write_bytes(vdf_entry())
    return profile


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "input.png"
    Image.new("RGBA", (16, 24), "red").save(path)
    return path


def test_reads_stored_unsigned_id_and_unicode():
    entry, = art.parse_shortcuts(vdf_entry(name="猫 café"))
    assert entry == art.Shortcut(0xF1234567, "猫 café", '"/games/play.sh"')


@pytest.mark.parametrize("data", [b"", b"\0shortcuts\0", vdf_entry()[:-1],
                                  vdf_entry() + b"junk", b"\x06bad\0"])
def test_malformed_shortcuts_are_rejected(data):
    with pytest.raises(art.ArtworkError):
        art.parse_shortcuts(data)


def test_discovers_profiles_and_deduplicates_steam_links(tmp_path, profile):
    home = tmp_path / "home"
    (home / ".steam").mkdir(parents=True)
    try:
        (home / ".steam/steam").symlink_to(profile.parents[1], target_is_directory=True)
        (home / ".steam/root").symlink_to(profile.parents[1], target_is_directory=True)
    except OSError:
        pytest.skip("This host does not permit creating symbolic links")
    assert art.discover_profiles(home) == [profile.resolve()]


def test_apply_preserves_shortcuts_unselected_slots_and_allows_undo(profile, image):
    entry, = art.shortcuts(profile)
    shortcut_bytes = (profile / "config/shortcuts.vdf").read_bytes()
    old, _, jpeg = art.artwork_paths(profile, entry, "portrait")
    old.write_bytes(b"old png")
    jpeg.write_bytes(b"old jpeg")
    hero = art.artwork_paths(profile, entry, "hero")[0]
    hero.write_bytes(b"untouched")
    backup = art.apply_artwork(profile, entry, {"portrait": image})
    assert old.read_bytes() == image.read_bytes()
    assert not jpeg.exists()
    assert hero.read_bytes() == b"untouched"
    assert (profile / "config/shortcuts.vdf").read_bytes() == shortcut_bytes
    art.undo_artwork(profile, backup)
    assert old.read_bytes() == b"old png"
    assert jpeg.read_bytes() == b"old jpeg"
    assert hero.read_bytes() == b"untouched"


def test_apply_uses_decoded_format_not_filename(profile, image):
    entry, = art.shortcuts(profile)
    disguised = image.with_suffix(".jpg")
    image.rename(disguised)
    art.apply_artwork(profile, entry, {"logo": disguised})
    assert art.artwork_paths(profile, entry, "logo")[0].read_bytes() == disguised.read_bytes()


def test_undo_removes_new_artwork(profile, image):
    entry, = art.shortcuts(profile)
    backup = art.apply_artwork(profile, entry, {slot: image for slot in art.SLOTS})
    art.undo_artwork(profile, backup)
    assert not list((profile / "config/grid").iterdir())


def test_invalid_image_prevents_entire_apply(profile, image, tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    entry, = art.shortcuts(profile)
    with pytest.raises(art.ArtworkError):
        art.apply_artwork(profile, entry, {"hero": image, "logo": bad})
    assert not list((profile / "config/grid").iterdir())


def test_changed_shortcut_is_not_modified(profile, image):
    entry, = art.shortcuts(profile)
    (profile / "config/shortcuts.vdf").write_bytes(vdf_entry(name="Renamed"))
    with pytest.raises(art.ArtworkError, match="changed"):
        art.apply_artwork(profile, entry, {"hero": image})
    assert not list((profile / "config/grid").iterdir())


def test_mid_apply_failure_rolls_back_every_slot(profile, image, monkeypatch):
    entry, = art.shortcuts(profile)
    portrait = art.artwork_paths(profile, entry, "portrait")[0]
    portrait.write_bytes(b"original")
    atomic = art._atomic_write
    fail = True
    def write(path, data):
        nonlocal fail
        if path.name.endswith("_hero.png") and fail:
            fail = False
            raise OSError("simulated disk failure")
        atomic(path, data)
    monkeypatch.setattr(art, "_atomic_write", write)
    with pytest.raises(OSError, match="disk failure"):
        art.apply_artwork(profile, entry, {"portrait": image, "hero": image})
    assert portrait.read_bytes() == b"original"
    assert not art.artwork_paths(profile, entry, "hero")[0].exists()


def test_undo_refuses_to_overwrite_later_changes(profile, image):
    entry, = art.shortcuts(profile)
    backup = art.apply_artwork(profile, entry, {"hero": image})
    path = art.artwork_paths(profile, entry, "hero")[0]
    path.write_bytes(b"newer artwork")
    with pytest.raises(art.ArtworkError, match="newer artwork"):
        art.undo_artwork(profile, backup)
    assert path.read_bytes() == b"newer artwork"


def test_failed_undo_restores_pre_undo_artwork(profile, image, monkeypatch):
    entry, = art.shortcuts(profile)
    portrait = art.artwork_paths(profile, entry, "portrait")[0]
    hero = art.artwork_paths(profile, entry, "hero")[0]
    portrait.write_bytes(b"original portrait")
    hero.write_bytes(b"original hero")
    backup = art.apply_artwork(profile, entry, {"portrait": image, "hero": image})
    atomic = art._atomic_write
    fail = True
    def write(path, data):
        nonlocal fail
        if path == hero and fail:
            fail = False
            raise OSError("simulated undo failure")
        atomic(path, data)
    monkeypatch.setattr(art, "_atomic_write", write)
    with pytest.raises(OSError, match="undo failure"):
        art.undo_artwork(profile, backup)
    assert portrait.read_bytes() == image.read_bytes()
    assert hero.read_bytes() == image.read_bytes()


def test_artwork_symlink_rejected(profile, image):
    entry, = art.shortcuts(profile)
    try:
        art.artwork_paths(profile, entry, "hero")[0].symlink_to(image)
    except OSError:
        pytest.skip("This host does not permit creating symbolic links")
    with pytest.raises(art.ArtworkError, match="links"):
        art.apply_artwork(profile, entry, {"hero": image})
    assert image.exists()


def test_backup_path_traversal_rejected(profile, image):
    entry, = art.shortcuts(profile)
    backup = art.apply_artwork(profile, entry, {"hero": image})
    manifest = json.loads((backup / "manifest.json").read_text())
    manifest["before"] = {"../shortcuts.vdf": True}
    manifest["after"] = {"../shortcuts.vdf": None}
    (backup / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(art.ArtworkError):
        art.undo_artwork(profile, backup)
