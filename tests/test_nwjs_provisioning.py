"""End-to-end synthetic NW.js provisioning; never contacts the CDN."""
import hashlib
import http.client
import io
from pathlib import Path
import struct
import sys
import tarfile
import urllib.error

import pytest

from megcfbt import tls
from megcfbt.router import ConversionError, build_source
from rpgmframe import runtime
from rpgmframe.builder import build_game


def elf(machine=183):
    data = bytearray(64)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, machine)
    return bytes(data)


def archive(*, machine=183, incomplete=False, unsafe=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        files = {"nw": elf(machine)}
        if not incomplete:
            files.update({"icudtl.dat": b"icu", "resources.pak": b"resources"})
        if unsafe:
            files["../../escaped"] = b"escape"
        for name, contents in files.items():
            member = tarfile.TarInfo(f"nwjs-v0.117.0-linux-arm64/{name}")
            member.size = len(contents)
            tar.addfile(member, io.BytesIO(contents))
    return stream.getvalue()


class Response(io.BytesIO):
    def __init__(self, contents, *, length=None):
        super().__init__(contents)
        self.headers = {"Content-Length": str(len(contents) if length is None else length)}


def install_network(monkeypatch, payload, *, metadata=None, fail_archive=None):
    calls = []
    digest = hashlib.sha256(payload).hexdigest()
    checksum = f"{digest}  nwjs-v0.117.0-linux-arm64.tar.gz\n".encode()
    def request(req, **kwargs):
        calls.append((req, kwargs))
        if req.full_url.endswith("SHASUMS256.txt"):
            return Response(checksum if metadata is None else metadata)
        if fail_archive:
            raise fail_archive
        return Response(payload)
    monkeypatch.setattr(tls.urllib.request, "urlopen", request)
    return calls


def write_source(path):
    for name, value in {
        "www/js/rpg_core.js": 'Utils.RPGMAKER_VERSION = "1.6.1";',
        "www/data/System.json": '{"gameTitle":"Synthetic MV"}',
        "www/index.html": "<html></html>",
        "package.json": '{"main":"www/index.html"}',
    }.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)


def assert_clean(manager):
    assert not list(manager.cache_dir.rglob(".download-*"))
    assert not list(manager.cache_dir.rglob("*.partial"))


def test_download_verifies_installs_arm64_and_reuses_cache(tmp_path, monkeypatch):
    calls = install_network(monkeypatch, archive())
    manager = runtime.RuntimeManager(tmp_path)
    result = manager.ensure_nwjs()
    assert runtime.read_elf_architecture(result / "nw") == "aarch64"
    assert len(calls) == 2
    for req, options in calls:
        assert req.get_header("User-agent") == runtime._HTTP_HEADERS["User-Agent"]
        assert req.get_header("Accept") == "*/*"
        if sys.platform.startswith("linux"):
            assert options["context"].check_hostname
        else:
            assert "context" not in options  # Preserve Windows' native trust selection.
    assert [options["timeout"] for _, options in calls] == [30, 60]
    assert manager.ensure_nwjs() == result and len(calls) == 2
    assert manager.list_cached() == [result]
    assert_clean(manager)


@pytest.mark.parametrize("metadata, message", [
    (b"", "no entry"), (b"nonsense", "no entry"),
    (b"abc  nwjs-v0.117.0-linux-arm64.tar.gz", "no entry"),
    (b"0" * 64 + b"  nwjs-v0.117.0-linux-arm64.tar.gz", "SHA256 mismatch"),
    (b"\xff", "decode checksum"),
])
def test_invalid_verification_data_cannot_populate_cache(tmp_path, monkeypatch, metadata, message):
    calls = install_network(monkeypatch, archive(), metadata=metadata)
    manager = runtime.RuntimeManager(tmp_path)
    with pytest.raises(runtime.RuntimeError, match=message):
        manager.ensure_nwjs()
    assert manager.list_cached() == []
    assert not manager.runtime_path().exists()
    if message == "no entry":
        assert len(calls) == 1
    assert_clean(manager)


@pytest.mark.parametrize("options, message", [
    ({"machine": 62}, "expected aarch64"),
    ({"incomplete": True}, "incomplete"),
    ({"unsafe": True}, "unsafe path"),
])
def test_rejects_invalid_runtime_archive(tmp_path, monkeypatch, options, message):
    install_network(monkeypatch, archive(**options))
    manager = runtime.RuntimeManager(tmp_path)
    with pytest.raises(runtime.RuntimeError, match=message):
        manager.ensure_nwjs()
    assert manager.list_cached() == []
    assert_clean(manager)


def test_invalid_cache_repaired_only_after_success(tmp_path, monkeypatch):
    manager = runtime.RuntimeManager(tmp_path)
    old = manager.runtime_path()
    old.mkdir(parents=True)
    (old / "nw").write_bytes(b"damaged previous cache")
    install_network(monkeypatch, archive(), fail_archive=OSError("offline"))
    with pytest.raises(runtime.RuntimeError):
        manager.ensure_nwjs()
    assert (old / "nw").read_bytes() == b"damaged previous cache"
    assert_clean(manager)
    install_network(monkeypatch, archive())
    assert manager.ensure_nwjs() == old
    assert manager._validate_cached(old)


def test_failed_install_restores_previous_cache(tmp_path, monkeypatch):
    manager = runtime.RuntimeManager(tmp_path)
    old = manager.runtime_path()
    old.mkdir(parents=True)
    (old / "nw").write_bytes(b"previous")
    install_network(monkeypatch, archive())
    rename = Path.rename
    def fail(source, destination):
        if source.parent.name == "extracted":
            raise OSError("simulated install failure")
        return rename(source, destination)
    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="install failure"):
        manager.ensure_nwjs()
    assert (old / "nw").read_bytes() == b"previous"
    assert_clean(manager)


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), http.client.IncompleteRead(b"partial")])
def test_interrupted_download_cleans_partial_and_preserves_destination(tmp_path, monkeypatch, failure):
    class Interrupted(Response):
        def read(self, *args):
            if self.tell():
                raise failure
            return super().read(3)
    monkeypatch.setattr(runtime, "open_url", lambda *a, **k: Interrupted(b"abcdef"))
    destination = tmp_path / "runtime.tar.gz"
    destination.write_bytes(b"previous verified archive")
    with pytest.raises(runtime.RuntimeError):
        runtime._download("https://example.invalid/runtime", destination)
    assert destination.read_bytes() == b"previous verified archive"
    assert not destination.with_name(destination.name + ".partial").exists()


def test_short_content_length_is_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "open_url", lambda *a, **k: Response(b"abc", length=10))
    with pytest.raises(runtime.RuntimeError, match="Interrupted"):
        runtime._download("https://example.invalid/runtime", tmp_path / "runtime")
    assert list(tmp_path.iterdir()) == []


def test_tls_error_preserves_cache_and_existing_output(tmp_path, monkeypatch):
    import ssl
    source, output = tmp_path / "source", tmp_path / "output"
    write_source(source)
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    output.mkdir()
    (output / "keep").write_text("valid old output")
    monkeypatch.setenv("RPGMFRAME_CACHE_DIR", str(tmp_path / "cache"))
    def fail(*a, **k):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "untrusted"))
    monkeypatch.setattr(tls.urllib.request, "urlopen", fail)
    with pytest.raises(ConversionError, match="server identity could not be verified"):
        build_source(source, output=output, archive=False, force=True)
    assert (output / "keep").read_text() == "valid old output"
    assert before == {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    manager = runtime.RuntimeManager()
    assert manager.list_cached() == []
    assert_clean(manager)


def test_missing_runtime_resolves_before_packaging_and_override_is_offline(tmp_path, monkeypatch):
    source = tmp_path / "source"
    write_source(source)
    manager = runtime.RuntimeManager(tmp_path / "cache")
    calls = install_network(monkeypatch, archive())
    result = build_game(source, output=tmp_path / "output", runtime_manager=manager)
    assert result.runtime_architecture == "aarch64"
    assert (result.output_path / "www/index.html").is_file()
    assert len(calls) == 2
    build_game(source, output=tmp_path / "cached-output", runtime_manager=manager)
    assert len(calls) == 2
    def no_network(*a, **k):
        pytest.fail("User runtime override attempted network access")
    monkeypatch.setattr(tls.urllib.request, "urlopen", no_network)
    result = build_game(source, output=tmp_path / "override-output", runtime=result.runtime_path)
    assert result.runtime_architecture == "aarch64"
