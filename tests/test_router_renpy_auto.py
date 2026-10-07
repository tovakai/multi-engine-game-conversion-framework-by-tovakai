from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from megcfbt import router
from megcfbt.models import UnifiedInspection


def test_renpy_build_resolves_runtime_automatically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "game"
    (source / "game").mkdir(parents=True)
    (source / "game/script.rpy").write_text("label start:\n    pass\n")
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    inspection = UnifiedInspection(
        source_path=source,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version="8.5.3",
        game_name="Synthetic",
        compatibility="LIKELY_COMPATIBLE",
        confidence="high",
        runtime_kind="official Ren'Py 8.5.3 ARM64 sdkarm",
        buildable=True,
    )
    monkeypatch.setattr(router, "inspect_source", lambda path: inspection)
    monkeypatch.setattr(router, "_inspect_prepared", lambda root: inspection)

    class FakeManager:
        def ensure_runtime(self, version, *, progress=None):
            assert version == "8.5.3"
            return runtime

    monkeypatch.setattr(router, "RenpyRuntimeManager", FakeManager)

    seen = {}

    def fake_build(source_path, **kwargs):
        seen["runtime"] = Path(kwargs["runtime"])
        out = Path(kwargs["output"])
        out.mkdir(parents=True)
        launcher = out / "Synthetic.sh"
        launcher.write_text("#!/bin/sh\n")
        return SimpleNamespace(
            launcher_path=launcher,
            warnings=[],
            display_name="Synthetic",
            game_name="Synthetic",
            source_version="8.5.3",
        )

    monkeypatch.setattr(router, "build_renpy_game", fake_build)
    monkeypatch.setattr(router, "create_tar_gz", lambda output, force=False: None)

    result = router.build_source(source, archive=False)

    assert seen["runtime"] == runtime
    assert result.engine == "renpy"
    assert result.engine_version == "8.5.3"
