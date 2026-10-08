from __future__ import annotations

import io
import json
from pathlib import Path

from megcfbt import artwork


def test_discovers_app_id_from_godotsteam_sidecar(tmp_path: Path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    (root / "steam_data.json").write_text(
        json.dumps({"app_id": "1942280"}),
        encoding="utf-8",
    )
    assert artwork.discover_steam_app_id(root) == "1942280"


def test_discovers_app_id_from_converted_game_subdirectory(tmp_path: Path) -> None:
    root = tmp_path / "Brotato-frame"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "steam_appid.txt").write_text("1942280\n", encoding="utf-8")
    assert artwork.discover_steam_app_id(root) == "1942280"


def test_fetch_official_artwork_is_best_effort(tmp_path: Path, monkeypatch) -> None:
    jpeg = b"\xff\xd8\xff" + b"fake-image"
    png = b"\x89PNG\r\n\x1a\n" + b"fake-logo"

    class Response(io.BytesIO):
        def __init__(self, data: bytes):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout=0):
        url = request.full_url
        if url.endswith("library_600x900_2x.jpg"):
            return Response(jpeg)
        if url.endswith("library_hero.jpg"):
            return Response(jpeg)
        if url.endswith("header.jpg"):
            return Response(jpeg)
        if url.endswith("logo.png"):
            return Response(png)
        raise AssertionError(url)

    monkeypatch.setattr(artwork.urllib.request, "urlopen", fake_urlopen)

    root = tmp_path / "build"
    root.mkdir()
    found = artwork.fetch_official_steam_artwork("1942280", root)

    assert (root / ".megcfbt/artwork/grid.jpg").read_bytes() == jpeg
    assert (root / ".megcfbt/artwork/hero.jpg").read_bytes() == jpeg
    assert (root / ".megcfbt/artwork/wide.jpg").read_bytes() == jpeg
    assert (root / ".megcfbt/artwork/logo.png").read_bytes() == png
    assert found["grid"].name == "grid.jpg"
    assert found["logo"].name == "logo.png"


def test_invalid_app_id_never_downloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        artwork.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )
    root = tmp_path / "build"
    root.mkdir()
    assert artwork.fetch_official_steam_artwork("not-a-number", root) == {}
