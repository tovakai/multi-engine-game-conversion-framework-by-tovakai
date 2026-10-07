from __future__ import annotations

import json
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
