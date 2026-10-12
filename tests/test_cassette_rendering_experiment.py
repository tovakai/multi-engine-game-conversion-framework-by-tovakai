import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "cassette_rendering_prepare",
    Path(__file__).parents[1] / "experiments/cassette-rendering/prepare.py",
)
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_merge_preserves_variants_and_other_rendering_settings():
    original = '; comment\n[graphics]\nresolution=Vector2(1920,1080)\n[rendering]\nquality/shadows/filter_mode=2\nquality/depth_prepass/enable=false\n[audio]\nvolume={"Master": 1.0}\n'
    merged = experiment.merge_depth_override(original)
    assert merged == original.replace(
        'quality/depth_prepass/enable=false\n',
        'quality/depth_prepass/enable=true\nquality/depth_prepass/disable_for_vendors=""\n',
    )
    assert experiment.merge_depth_override(merged) == merged


@pytest.mark.parametrize("text", [
    '[rendering]\n[rendering]\n',
    '[rendering]\nquality/depth_prepass/enable=false\nquality/depth_prepass/enable=true\n',
])
def test_ambiguous_overrides_require_review(text):
    with pytest.raises(ValueError, match="Duplicate"):
        experiment.merge_depth_override(text)


def test_packages_keep_control_bytes_and_isolate_settings_and_saves(tmp_path):
    source = tmp_path / "control"
    (source / "game").mkdir(parents=True)
    (source / "game/CassetteBeasts.pck").write_bytes(b"synthetic test pack")
    original = '[rendering]\nquality/depth_prepass/enable=false\n[other]\nvalue=Vector2(1,2)\n'
    (source / "game/override.cfg").write_text(original)
    (source / "runtime.json").write_text(json.dumps({"engine_version": "3.5.1", "pack_loading": "main-pack"}))
    (source / "launch.sh").write_text('#!/bin/bash\n')
    saves = tmp_path / "saves"
    saves.mkdir()
    (saves / "save").write_bytes(b"synthetic save")
    target = tmp_path / "comparison"
    experiment.prepare(source, target, saves)
    assert (source / "game/override.cfg").read_text() == original
    for name in ("baseline", "depth-prepass", "gles2"):
        package = target / name / "payload"
        assert (package / "game/CassetteBeasts.pck").read_bytes() == b"synthetic test pack"
        assert not (package / "override.cfg").exists()
        assert (target / name / "profile/data/CassetteBeasts/save").read_bytes() == b"synthetic save"
        launcher = (target / f"launch-{name}.sh").read_text()
        assert "XDG_DATA_HOME" in launcher and "pipefail" in launcher
        assert ("--video-driver GLES2" if name == "gles2" else "--video-driver GLES3") in launcher
    assert (target / "baseline/payload/game/override.cfg").read_text() == original
    assert (target / "gles2/payload/game/override.cfg").read_text() == original
    assert (target / "depth-prepass/payload/game/override.cfg").read_text() == experiment.merge_depth_override(original)
    (target / "depth-prepass/profile/data/CassetteBeasts/save").write_bytes(b"changed")
    assert (saves / "save").read_bytes() == b"synthetic save"
    assert (target / "baseline/profile/data/CassetteBeasts/save").read_bytes() == b"synthetic save"
    with pytest.raises(ValueError, match="new destination"):
        experiment.prepare(source, target, saves)
