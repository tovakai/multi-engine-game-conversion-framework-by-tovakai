from io import BytesIO
import json
import urllib.error
import urllib.request

from PIL import Image
import pytest

from steamartwork import steamgriddb as sgdb
from steamartwork.backend import ArtworkError


def png():
    buffer = BytesIO()
    Image.new("RGBA", (10, 10), "blue").save(buffer, "PNG")
    return buffer.getvalue()


def test_fetch_stages_all_types_without_saving_key(tmp_path, monkeypatch):
    calls = []
    def request(url, *, api_key=None, limit=None):
        calls.append((url, api_key))
        if "/games/id/123" in url:
            payload = {"success": True, "data": {"id": 123, "name": "Example"}}
        elif "/api/v2/" in url:
            payload = {"success": True, "data": [{"url": "https://cdn2.steamgriddb.com/test.png", "score": 10}]}
        else:
            assert api_key is None
            return png()
        return json.dumps(payload).encode()
    monkeypatch.setattr(sgdb, "request_bytes", request)
    title, images, warnings = sgdb.fetch_artwork("secret-key", "123", tmp_path)
    assert title == "Example"
    assert set(images) == set(sgdb.QUERIES)
    assert warnings == []
    assert all(path.suffix == ".png" for path in images.values())
    assert all(b"secret-key" not in path.read_bytes() for path in tmp_path.iterdir())
    assert any("dimensions=600x900" in url for url, _ in calls)
    assert any("dimensions=920x430" in url for url, _ in calls)


def test_fetch_only_requested_slots_and_reports_missing(tmp_path, monkeypatch):
    calls = []
    def api(path, key):
        calls.append(path)
        if path.startswith("games/"):
            return {"id": 123, "name": "Example"}
        return []
    monkeypatch.setattr(sgdb, "api_json", api)
    _, images, warnings = sgdb.fetch_artwork("key", "123", tmp_path, slots=["hero"])
    assert not images
    assert warnings == ["hero: no suitable static image"]
    assert len(calls) == 2 and calls[1].startswith("heroes/")


@pytest.mark.parametrize("key,game", [("", "1"), ("key\n", "0"), ("key", "steam/123"), ("key", "-1")])
def test_invalid_lookup_rejected_without_network(tmp_path, key, game, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Invalid lookup must not access network")
    monkeypatch.setattr(sgdb, "request_bytes", no_network)
    with pytest.raises(ArtworkError):
        sgdb.fetch_artwork(key, game, tmp_path)


@pytest.mark.parametrize("url", ["http://cdn.steamgriddb.com/x", "https://steamgriddb.com.evil.test/x",
                                 "https://user:pass@steamgriddb.com/x", "file:///tmp/image.png"])
def test_untrusted_asset_url_rejected(url):
    assert not sgdb.trusted_url(url)
    with pytest.raises(ArtworkError):
        sgdb.request_bytes(url)


def test_authentication_error_is_clear_and_redacted(monkeypatch):
    class Opener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "secret-key", {}, None)
    monkeypatch.setattr(sgdb.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(ArtworkError, match="API key was rejected") as error:
        sgdb.request_bytes(sgdb.API + "/games/id/1", api_key="secret-key")
    assert "secret-key" not in str(error.value)


def test_authenticated_redirect_cannot_forward_key_to_cdn():
    req = urllib.request.Request(sgdb.API + "/games/id/1", headers={"Authorization": "Bearer secret-key"})
    with pytest.raises(ArtworkError, match="authentication redirect"):
        sgdb._Redirect().redirect_request(req, None, 302, "Found", {}, "https://cdn.steamgriddb.com/x")


def test_bad_top_asset_falls_back_to_valid_alternative(tmp_path, monkeypatch):
    def api(path, key):
        if path.startswith("games/"):
            return {"id": 123, "name": "Example"}
        return [{"url": "https://cdn.steamgriddb.com/bad", "score": 20},
                {"url": "https://cdn.steamgriddb.com/good", "score": 10}]
    monkeypatch.setattr(sgdb, "api_json", api)
    monkeypatch.setattr(sgdb, "request_bytes", lambda url: b"invalid" if url.endswith("bad") else png())
    _, images, warnings = sgdb.fetch_artwork("key", "123", tmp_path, slots=["logo"])
    assert set(images) == {"logo"}
    assert not warnings
