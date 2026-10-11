from __future__ import annotations

import json
import zipfile
from pathlib import Path

from megcfbt.router import build_source, inspect_source


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _arm64_runtime(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    header = bytearray(20)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[18:20] = (183).to_bytes(2, "little")
    (root / "nw").write_bytes(bytes(header))
    return root


def test_detects_construct_2_export(tmp_path: Path) -> None:
    root = tmp_path / "construct2-game"
    _write(root / "index.html", "<html><canvas id='c2canvas'></canvas></html>")
    _write(root / "c2runtime.js", "// Construct 2 runtime")
    _write(root / "data.js", "window.cr_getC2Runtime = true;")
    _write(
        root / "package.json",
        json.dumps({"name": "c2-test", "window": {"title": "Synthetic C2"}}),
    )

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "construct2"
    assert result.engine_label == "Construct 2"
    assert result.game_name == "Synthetic C2"
    assert result.runtime_kind == "nwjs"
    assert result.compatibility == "needs_testing"
    assert result.buildable is True
    assert any("c2runtime.js" in evidence for evidence in result.evidence)


def test_detects_construct_3_scripts_runtime(tmp_path: Path) -> None:
    root = tmp_path / "construct3-game"
    _write(root / "www/index.html", "<html></html>")
    _write(root / "www/scripts/c3runtime.js", "// Construct 3 runtime")
    _write(root / "www/scripts/main.js", "// generated project")
    _write(
        root / "package.json",
        json.dumps({"name": "c3-test", "window": {"title": "Synthetic C3"}}),
    )

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "construct3"
    assert result.engine_label == "Construct 3"
    assert result.game_name == "Synthetic C3"
    assert result.runtime_kind == "nwjs"
    assert result.compatibility == "needs_testing"
    assert result.buildable is True
    assert any("scripts/c3runtime.js" in evidence for evidence in result.evidence)


def test_builds_construct_2_with_supplied_arm64_nwjs(tmp_path: Path) -> None:
    source = tmp_path / "construct2-game"
    _write(source / "index.html", "<html></html>")
    _write(source / "c2runtime.js", "// Construct 2 runtime")
    _write(source / "data.js", "// game data")

    runtime = _arm64_runtime(tmp_path / "runtime")
    output = tmp_path / "out"

    result = build_source(
        source,
        output=output,
        backend_runtime=runtime,
        archive=False,
    )

    assert result.engine == "construct2"
    assert result.output_path == output
    assert (output / "www/index.html").is_file()
    assert (output / "www/c2runtime.js").is_file()
    assert (output / "launch.sh").is_file()
    package = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert package["main"] == "www/index.html"
    assert not (output / "www/js/rpgmframe-compat.js").exists()


def test_builds_construct_3_with_supplied_arm64_nwjs(tmp_path: Path) -> None:
    source = tmp_path / "construct3-game"
    _write(source / "index.html", "<html></html>")
    _write(source / "scripts/c3runtime.js", "// Construct 3 runtime")
    _write(source / "scripts/main.js", "// generated project")

    runtime = _arm64_runtime(tmp_path / "runtime")
    output = tmp_path / "out"

    result = build_source(
        source,
        output=output,
        backend_runtime=runtime,
        archive=False,
    )

    assert result.engine == "construct3"
    assert (output / "www/scripts/c3runtime.js").is_file()
    assert (output / "www/scripts/main.js").is_file()


def test_detects_construct_2_inside_package_nw(tmp_path: Path) -> None:
    root = tmp_path / "construct2-packaged"
    root.mkdir()
    package_nw = root / "package.nw"
    with zipfile.ZipFile(package_nw, "w") as archive:
        archive.writestr("index.html", "<html></html>")
        archive.writestr("c2runtime.js", "// Construct 2 runtime")
        archive.writestr("data.js", "// game data")
        archive.writestr(
            "package.json",
            json.dumps({"name": "packed-c2", "window": {"title": "Packed C2"}}),
        )

    result = inspect_source(root)

    assert result.engine == "construct2"
    assert result.game_name == "Packed C2"
    assert result.buildable is True
    assert any("package.nw::c2runtime.js" in evidence for evidence in result.evidence)
    assert any("package.nw" in warning for warning in result.warnings)


def test_builds_construct_2_from_package_nw(tmp_path: Path) -> None:
    source = tmp_path / "construct2-packaged"
    source.mkdir()
    package_nw = source / "package.nw"
    with zipfile.ZipFile(package_nw, "w") as archive:
        archive.writestr("index.html", "<html></html>")
        archive.writestr("c2runtime.js", "// Construct 2 runtime")
        archive.writestr("data.js", "// game data")
        archive.writestr(
            "package.json",
            json.dumps({"name": "packed-c2", "window": {"title": "Packed C2"}}),
        )
    _write(source / "steam_appid.txt", "12345\n")
    _write(source / "old-runtime.exe", "windows baggage")
    _write(source / "v8_context_snapshot.bin", "Windows V8 snapshot")

    runtime = _arm64_runtime(tmp_path / "runtime")
    _write(runtime / "v8_context_snapshot.bin", "ARM64 V8 snapshot")
    output = tmp_path / "out"

    result = build_source(
        source,
        output=output,
        backend_runtime=runtime,
        archive=False,
    )

    assert result.engine == "construct2"
    assert (output / "www/index.html").is_file()
    assert (output / "www/c2runtime.js").is_file()
    assert (output / "steam_appid.txt").read_text(encoding="utf-8") == "12345\n"
    assert not (output / "package.nw").exists()
    assert not (output / "old-runtime.exe").exists()
    assert (output / "v8_context_snapshot.bin").read_text() == "ARM64 V8 snapshot"
    package = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert package["main"] == "www/index.html"


def test_stock_construct3_worker_export_uses_dom_fallback(tmp_path):
    from rpgmframe.construct import install_construct3_compatibility
    payload = tmp_path / 'www'
    main = payload / 'scripts/main.js'
    source = 'const enableWorker=true; window.c3=new self.RuntimeInterface({useWorker:enableWorker});'
    _write(main, source)
    package = tmp_path / 'package.json'
    _write(package, json.dumps({'chromium-args': '--enable-node-worker --allow-file-access-from-files',
                               'window': {'title': 'keep'}}))
    assert install_construct3_compatibility(payload, package)
    assert 'const enableWorker=false' in main.read_text()
    value = json.loads(package.read_text())
    assert value['chromium-args'] == '--allow-file-access-from-files'
    assert value['window']['title'] == 'keep'
    assert not install_construct3_compatibility(payload, package)


def test_custom_construct_bootstrap_is_preserved(tmp_path):
    from rpgmframe.construct import install_construct3_compatibility
    main = tmp_path / 'scripts/main.js'
    source = 'const enableWorker=true; customBootstrap(enableWorker);'
    _write(main, source)
    assert not install_construct3_compatibility(tmp_path, tmp_path / 'missing-package.json')
    assert main.read_text() == source


def test_rejects_unsafe_package_nw_paths(tmp_path: Path) -> None:
    source = tmp_path / "construct2-unsafe"
    source.mkdir()
    package_nw = source / "package.nw"
    with zipfile.ZipFile(package_nw, "w") as archive:
        archive.writestr("index.html", "<html></html>")
        archive.writestr("c2runtime.js", "// Construct 2 runtime")
        archive.writestr("../escape.txt", "nope")

    runtime = _arm64_runtime(tmp_path / "runtime")

    import pytest
    from megcfbt.router import ConversionError

    with pytest.raises(ConversionError, match="unsafe path"):
        build_source(
            source,
            output=tmp_path / "out",
            backend_runtime=runtime,
            archive=False,
        )
