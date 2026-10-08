"""SteamGridDB artwork fallback: no credentials leak, no fuzzy mismatches."""
from __future__ import annotations

import json
import zipfile
from email.message import Message

from megcfbt.artwork import complete_frame_artwork
from megcfbt.frame_package import create_frame_zip, write_frame_metadata
from megcfbt import steamgriddb


class Response:
    def __init__(self, data, mime):
        self.data = data
        self.headers = Message()
        self.headers["Content-Type"] = mime

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        return False

    def read(self, limit):
        return self.data[:limit]


JPEG = b"\xff\xd8\xff" + b"artwork"
PNG = b"\x89PNG\r\n\x1a\n" + b"artwork"


def setup_build(tmp_path):
    root = tmp_path / "MyPigPrincess-frame"
    root.mkdir()
    launcher = root / "launch.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    write_frame_metadata(
        root,
        name="My Pig Princess",
        launcher_path=launcher,
        engine="renpy",
        engine_version="8.0.1",
    )
    return root


def mock_service(monkeypatch, *, search=None, assets=True):
    visited = []

    def mock_json(path, key):
        assert key == "test-key-not-for-public"
        visited.append(path)
        if path.startswith("search/autocomplete/"):
            return {"success": True, "data": search if search is not None else [
                {"id": 123, "name": "My Pig Princess", "verified": True},
            ]}
        if path.startswith("games/id/"):
            return {"success": True, "data": {"id": 123, "name": "My Pig Princess"}}
        if path.startswith("games/steam/"):
            return {"success": True, "data": {"id": 123, "name": "My Pig Princess"}}
        if not assets:
            return {"success": True, "data": []}
        return {"success": True, "data": [
            {"id": 9, "score": 50, "tags": [],
             "url": "https://cdn2.steamgriddb.com/file/sgdb-cdn/image.png"},
            {"id": 8, "score": 100, "tags": ["nsfw"],
             "url": "https://cdn2.steamgriddb.com/file/sgdb-cdn/explicit.png"},
        ]}

    def urlopen(request, timeout):
        assert "Authorization" not in request.headers
        visited.append(request.full_url)
        return Response(PNG, "image/png")

    monkeypatch.setattr(steamgriddb, "_api_json", mock_json)
    monkeypatch.setattr(steamgriddb.urllib.request, "urlopen", urlopen)
    return visited


def test_missing_key_is_disabled_and_does_not_access_network(tmp_path, monkeypatch):
    monkeypatch.delenv("STEAMGRIDDB_API_KEY", raising=False)
    root = setup_build(tmp_path)
    monkeypatch.setattr(steamgriddb, "_api_json", lambda *a: 1/0)
    messages = []
    result = complete_frame_artwork(root, game_name="My Pig Princess", progress=messages.append)
    assert result == {}
    assert any("disabled" in line for line in messages)


def test_nonsteam_exact_name_fetches_static_art_and_bundles_zip(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    calls = mock_service(monkeypatch)
    messages = []
    result = complete_frame_artwork(root, game_name="My Pig Princess", progress=messages.append)
    assert set(result) == {"grid", "wide", "hero", "logo"}
    assert result["grid"].read_bytes() == PNG
    assert all("nsfw=false" in c for c in calls if "/game/" in c)
    assert any(c.endswith("/image.png") for c in calls)
    assert not any(c.endswith("/explicit.png") for c in calls)
    assert "search/autocomplete/My%20Pig%20Princess" in calls
    meta = json.loads((root / ".megcfbt/package.json").read_text())
    assert meta["artwork"]["slots"] == {
        "grid": "steamgriddb",
        "wide": "steamgriddb",
        "hero": "steamgriddb",
        "logo": "steamgriddb",
    }
    assert meta["artwork"]["steamgriddb"] == {
        "provider": "steamgriddb", "game_id": 123, "matched_name": "My Pig Princess"
    }
    assert "test-key-not-for-public" not in json.dumps(meta)
    package = create_frame_zip(root)
    with zipfile.ZipFile(package) as zf:
        names = zf.namelist()
        for slot in ("grid", "wide", "hero", "logo"):
            assert f"MyPigPrincess-frame/.megcfbt/artwork/{slot}.png" in names
        assert "test-key-not-for-public" not in zf.read("MyPigPrincess-frame/.megcfbt/package.json").decode()
        installer = zf.read("MyPigPrincess-frame/.megcfbt/install-to-steam.py").decode()
        assert "apply_artwork" in installer
        assert "find_shortcuts" in installer
    assert any("matched: My Pig Princess" in line for line in messages)


def test_ambiguous_exact_matches_skip(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    calls = mock_service(monkeypatch, search=[
        {"id": 123, "name": "MY PIG PRINCESS"},
        {"id": 456, "name": "My Pig Princess!"},
    ])
    logs = []
    assert complete_frame_artwork(root, game_name="My Pig Princess", progress=logs.append) == {}
    assert any("ambiguous" in line for line in logs)
    assert not any("/game/" in line for line in calls)


def test_near_but_not_exact_name_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    calls = mock_service(monkeypatch, search=[{"id": 123, "name": "My Pig Princess Deluxe"}])
    logs = []
    assert complete_frame_artwork(root, game_name="My Pig Princess", progress=logs.append) == {}
    assert any("no reliable match" in line for line in logs)
    assert not any("/game/" in line for line in calls)


def test_manual_cover_kept_and_only_empty_slots_filled(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    art = root / ".megcfbt/artwork"
    art.mkdir()
    (art / "grid.jpg").write_bytes(b"manually-chosen")
    calls = mock_service(monkeypatch)
    result = complete_frame_artwork(root, game_name="My Pig Princess")
    assert result["grid"].read_bytes() == b"manually-chosen"
    assert not any("dimensions=600x900" in q for q in calls)
    assert (art / "hero.png").read_bytes() == PNG
    meta = json.loads((root / ".megcfbt/package.json").read_text())
    assert meta["artwork"]["slots"]["grid"] == "manual"


def test_existing_official_assets_wins_over_sgdb(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    (root / "steam_appid.txt").write_text("12345\n")
    def fake_steam(_root, progress=None):
        art = _root / ".megcfbt/artwork"
        art.mkdir(parents=True, exist_ok=True)
        for slot in ("grid", "wide", "hero", "logo"):
            (art / f"{slot}.jpg").write_bytes(JPEG)
        return {slot: art / f"{slot}.jpg" for slot in ("grid", "wide", "hero", "logo")}
    monkeypatch.setattr("megcfbt.artwork.fetch_official_steam_artwork", fake_steam)
    monkeypatch.setattr(steamgriddb, "_api_json", lambda *_: 1/0)
    result = complete_frame_artwork(root, game_name="My Pig Princess")
    assert len(result) == 4
    assert all(x.read_bytes() == JPEG for x in result.values())
    meta = json.loads((root / ".megcfbt/package.json").read_text())
    assert set(meta["artwork"]["slots"].values()) == {"official_steam"}


def test_official_missing_slot_falls_back_using_exact_steam_id(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    (root / "steam_appid.txt").write_text("12345\n")
    monkeypatch.setattr("megcfbt.artwork.fetch_official_steam_artwork", lambda *a, **kw: {})
    calls = mock_service(monkeypatch)
    result = complete_frame_artwork(root, game_name="Totally Wrong Game Name")
    assert set(result) == {"grid", "wide", "hero", "logo"}
    assert "games/steam/12345" in calls
    assert not any("search/autocomplete" in line for line in calls)


def test_explicit_sgdb_game_id_avoids_name_matching(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    calls = mock_service(monkeypatch, search=[])
    result = complete_frame_artwork(root, game_name="Broken Title", steamgriddb_game_id=123)
    assert "grid" in result
    assert "games/id/123" in calls


def test_network_failures_do_not_block_conversion(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    monkeypatch.setattr(steamgriddb, "_api_json", lambda *a: (_ for _ in ()).throw(OSError("offline")))
    logs = []
    assert complete_frame_artwork(root, game_name="My Pig Princess", progress=logs.append) == {}
    assert any("lookup skipped" in line for line in logs)


def test_untrusted_asset_host_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)

    def mock_json(path, key):
        if path.startswith("search/"):
            return {"success": True, "data": [{"name": "My Pig Princess", "id": 123}]}
        return {"success": True, "data": [{"id": 1, "url": "https://evil.example/image.png", "score": 100}]}

    monkeypatch.setattr(steamgriddb, "_api_json", mock_json)
    monkeypatch.setattr(steamgriddb.urllib.request, "urlopen", lambda *a, **kw: 1/0)
    assert complete_frame_artwork(root, game_name="My Pig Princess") == {}


def test_nsfw_opt_in_can_include_explicit_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    monkeypatch.setenv("STEAMGRIDDB_NSFW", "any")
    root = setup_build(tmp_path)
    calls = mock_service(monkeypatch)
    result = complete_frame_artwork(root, game_name="My Pig Princess")
    assert "grid" in result
    assert any("nsfw=any" in c for c in calls if "/game/" in c)


def test_artwork_cli_refreshes_existing_build_without_reconversion(tmp_path, monkeypatch, capsys):
    from megcfbt.cli import main

    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    mock_service(monkeypatch)
    assert main(["artwork", str(root), "--repackage"]) == 0
    output = capsys.readouterr().out
    assert "Updated Frame package" in output
    assert (root / ".megcfbt/artwork/grid.png").is_file()
    assert root.parent.joinpath("MyPigPrincess-linux-aarch64.zip").is_file()


def test_invalid_explicit_id_does_not_crash_conversion(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMGRIDDB_API_KEY", "test-key-not-for-public")
    root = setup_build(tmp_path)
    messages = []
    result = complete_frame_artwork(
        root, game_name="My Pig Princess", steamgriddb_game_id=-1,
        progress=messages.append,
    )
    assert result == {}
    assert any("positive integer" in line for line in messages)
