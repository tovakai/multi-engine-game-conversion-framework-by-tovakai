import atexit
import gc
import importlib.util
import io
import json
import pickle
import struct
import sys
import textwrap
import types
import zlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_audit():
    spec = importlib.util.spec_from_file_location("asset_audit", ROOT / "scripts/renpy_asset_audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_index_rejects_globals():
    module = load_audit()
    with pytest.raises(ValueError, match="globals"):
        module.IndexUnpickler(io.BytesIO(pickle.dumps(Path("anything")))).load()


def test_asset_audit_reads_png_and_prefixed_archive(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 3200, 2960)
    (game / "loose.png").write_bytes(png)
    key = 12345
    prefix = png[:8]
    body = png[8:]
    offset = 40 + len(body)
    header = ("RPA-3.0 %016x %08x\n" % (offset, key)).encode().ljust(40, b" ")
    index = {b"archive.png": [(40 ^ key, len(body) ^ key, prefix)]}
    (game / "archive.rpa").write_bytes(header + body + zlib.compress(pickle.dumps(index, protocol=4)))
    result = load_audit().audit(tmp_path)
    assert result["entries"] == 2
    assert result["archives"][0]["entries"] == 1
    assert all(row["dimensions"] == (3200, 2960) for row in result["largest_png_surfaces"])
    assert result["largest_png_surfaces"][0]["rgba_mib"] == pytest.approx(36.1328125)


def runtime(monkeypatch, tmp_path, enabled):
    renpy = types.ModuleType("renpy")
    renpy.__path__ = []
    config = types.SimpleNamespace(image_cache_size_mb=300, image_cache_size=8,
                                   screen_width=1600, screen_height=1200,
                                   predict_statements=32, predict_screens=True,
                                   interact_callbacks=[])
    renpy.config = config
    renpy.game = types.SimpleNamespace(less_memory=False)
    renpy.version = "Ren'Py 7.5.0.test"
    renpy.get_renderer_info = lambda: {"renderer": "gl2"}
    modules = {"renpy": renpy}
    for name in ("renpy.loader", "renpy.display", "renpy.display.im", "renpy.display.core", "renpy.display.screen", "renpy.exports"):
        module = types.ModuleType(name)
        module.__path__ = []
        modules[name] = module
        parent, _, attribute = name.rpartition(".")
        setattr(modules[parent], attribute, module)
    class Cache:
        def __init__(self):
            self.cache = {}
        def get(self, image, *args, **kwargs):
            self.cache[image] = types.SimpleNamespace(texture=object())
            return 42
    class Image:
        def load(self):
            return 17
    modules["renpy.display.im"].Cache = Cache
    modules["renpy.display.im"].Image = Image
    modules["renpy.display.core"].Interface = type("Interface", (), {"draw_screen": lambda self: "drawn"})
    modules["renpy.display.core"].pygame = types.SimpleNamespace(MOUSEBUTTONDOWN=1, MOUSEBUTTONUP=2, KEYDOWN=3)
    modules["renpy.display.screen"].ScreenDisplayable = type("ScreenDisplayable", (), {})
    modules["renpy.loader"].SubFile = type("SubFile", (), {"read": lambda self: b"data"})
    modules["renpy.exports"].free_memory = lambda: "original"
    renpy.free_memory = renpy.exports.free_memory
    renpy.display.draw = None
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    callbacks = []
    monkeypatch.setattr(atexit, "register", callbacks.append)
    # The runtime intentionally wraps this real standard-library function.
    # Restore it at test teardown so instrumentation cannot leak across tests.
    monkeypatch.setattr(gc, "collect", gc.collect)
    monkeypatch.delenv("RENFRAME_CACHE_MB", raising=False)
    monkeypatch.delenv("RENFRAME_PREDICT_STATEMENTS", raising=False)
    monkeypatch.delenv("RENFRAME_CPROFILE", raising=False)
    monkeypatch.setenv("RENFRAME_DIAGNOSTICS", "1" if enabled else "0")
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("RENFRAME_TRACE", str(path))
    code = textwrap.dedent((ROOT / "renframe/diagnostics.rpy").read_text().split("init 999 python:\n", 1)[1])
    return renpy, callbacks, path, code


def test_disabled_diagnostics_preserves_runtime(monkeypatch, tmp_path):
    renpy, callbacks, path, code = runtime(monkeypatch, tmp_path, False)
    original = renpy.display.im.Cache.get
    exec(code, {"renpy": renpy})
    assert renpy.display.im.Cache.get is original
    assert renpy.config.image_cache_size == 8
    assert renpy.config.image_cache_size_mb == 300
    assert not path.exists()
    assert not callbacks


def test_enabled_diagnostics_observes_cache_without_changing_results(monkeypatch, tmp_path):
    renpy, callbacks, path, code = runtime(monkeypatch, tmp_path, True)
    exec(code, {"renpy": renpy})
    cache = renpy.display.im.Cache()
    assert cache.get("asset") == 42
    assert cache.get("asset") == 42
    assert cache.get("predicted", True) == 42
    assert renpy.free_memory() == "original"
    callbacks[0]()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    totals = records[-1]["operations"]
    assert totals["cache.demand.absent"]["calls"] == 1
    assert totals["cache.demand.texture"]["calls"] == 1
    assert totals["cache.predict.absent"]["calls"] == 1
    assert totals["memory.free_inclusive"]["calls"] == 1
    assert renpy.config.image_cache_size == 8


def test_cache_override_is_explicit_and_bounded(monkeypatch, tmp_path):
    renpy, _, _, code = runtime(monkeypatch, tmp_path, False)
    monkeypatch.setenv("RENFRAME_CACHE_MB", "384")
    exec(code, {"renpy": renpy})
    assert renpy.config.image_cache_size_mb == 384
    assert renpy.config.image_cache_size is None
    monkeypatch.setenv("RENFRAME_CACHE_MB", "4096")
    with pytest.raises(Exception, match="between"):
        exec(code, {"renpy": renpy})


def test_input_to_first_draw_is_observed_without_swallowing_input(monkeypatch, tmp_path):
    renpy, callbacks, path, code = runtime(monkeypatch, tmp_path, True)
    event = types.SimpleNamespace(type=1)
    interface_class = renpy.display.core.Interface
    interface_class.event_poll = lambda self: event
    exec(code, {"renpy": renpy})
    interface = interface_class()
    assert interface.event_poll() is event
    assert interface.draw_screen() == "drawn"
    assert interface.draw_screen() == "drawn"
    callbacks[0]()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len([row for row in records if row["type"] == "input"]) == 1
    assert len([row for row in records if row["type"] == "first_draw_after_input"]) == 1


def test_trace_summary_handles_partial_tail_and_missing_hooks(tmp_path):
    spec = importlib.util.spec_from_file_location("profile_summary", ROOT / "scripts/renpy_profile_summary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "trace.jsonl"
    records = [dict(type="unavailable_hook", operation="renderer.texture_inclusive"),
               dict(type="first_draw_after_input", duration_ms=10),
               dict(type="first_draw_after_input", duration_ms=500),
               dict(type="aggregate", operations={"loader.open": {"calls": 2}})]
    path.write_text("\n".join(json.dumps(row) for row in records) + '\n{"incomplete":')
    result = module.summarize(path)
    assert result["input_to_next_draw"]["p95_ms"] == 500
    assert result["unavailable_hooks"] == ["renderer.texture_inclusive"]
    assert result["last_aggregate"]["operations"]["loader.open"]["calls"] == 2
