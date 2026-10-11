from __future__ import annotations

from email.message import Message

from megcfbt.artwork import fetch_official_steam_artwork


class _Response:
    def __init__(self, data: bytes, mime: str):
        self._data = data
        self.headers = Message()
        self.headers["Content-Type"] = mime

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        return self._data


def test_fetches_full_official_steam_artwork_set(tmp_path, monkeypatch):
    build = tmp_path / "Brotato-frame"
    game = build / "game"
    game.mkdir(parents=True)
    (game / "steam_appid.txt").write_text("1942280\n", encoding="utf-8")

    jpeg = b"\xff\xd8\xfffake-jpeg"
    png = b"\x89PNG\r\n\x1a\nfake-png"
    requested: list[str] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        url = request.full_url
        requested.append(url)
        if url.endswith("/logo.png"):
            return _Response(png, "image/png")
        return _Response(jpeg, "image/jpeg")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = fetch_official_steam_artwork(build)

    assert set(result) == {"grid", "wide", "hero", "logo"}
    assert (build / ".megcfbt/artwork/grid.jpg").read_bytes() == jpeg
    assert (build / ".megcfbt/artwork/wide.jpg").read_bytes() == jpeg
    assert (build / ".megcfbt/artwork/hero.jpg").read_bytes() == jpeg
    assert (build / ".megcfbt/artwork/logo.png").read_bytes() == png
    assert any(url.endswith("/library_600x900.jpg") for url in requested)
    assert any(url.endswith("/header.jpg") for url in requested)
    assert any(url.endswith("/library_hero.jpg") for url in requested)
    assert any(url.endswith("/logo.png") for url in requested)


def test_manual_portrait_is_preserved_while_other_art_is_fetched(tmp_path, monkeypatch):
    build = tmp_path / "Example-frame"
    game = build / "game"
    art = build / ".megcfbt" / "artwork"
    game.mkdir(parents=True)
    art.mkdir(parents=True)
    (game / "steam_appid.txt").write_text("12345\n", encoding="utf-8")
    manual = b"manual-cover"
    (art / "grid.png").write_bytes(manual)

    jpeg = b"\xff\xd8\xffother"
    png = b"\x89PNG\r\n\x1a\nlogo"
    requested: list[str] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        requested.append(request.full_url)
        if request.full_url.endswith("/logo.png"):
            return _Response(png, "image/png")
        return _Response(jpeg, "image/jpeg")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = fetch_official_steam_artwork(build)

    assert result["grid"] == art / "grid.png"
    assert (art / "grid.png").read_bytes() == manual
    assert not any(url.endswith("/library_600x900.jpg") for url in requested)
    assert (art / "wide.jpg").is_file()
    assert (art / "hero.jpg").is_file()
    assert (art / "logo.png").is_file()
