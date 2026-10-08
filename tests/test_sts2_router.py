import json
from pathlib import Path
from unittest import mock

import pytest

from megcfbt.router import ConversionError, build_source, inspect_source
from megcfbt import sts2
from megcfbt.models import UnifiedInspection


def source(root):
    (root / "data_sts2_windows_x86_64").mkdir()
    (root / "data_sts2_windows_x86_64/sts2.dll").write_bytes(b"synthetic detection marker")
    (root / "SlayTheSpire2.pck").write_bytes(b"synthetic detection marker")
    (root / "release_info.json").write_text(json.dumps({"version": "v0.107.1", "commit": "59260271"}))


def test_sts2_unsupported_build_has_dedicated_diagnostics(tmp_path):
    source(tmp_path)
    result = inspect_source(tmp_path)
    assert result.backend == "sts2"
    assert result.compatibility == "unsupported"
    assert not result.buildable
    assert any("v0.98.2 / f4eeecc6" in message for message in result.warnings)
    with pytest.raises(ConversionError, match="v0.98.2 / f4eeecc6"):
        build_source(tmp_path, archive=False)


def test_sts2_missing_tools_never_falls_through_to_generic_godot(tmp_path):
    source(tmp_path)
    with mock.patch.object(sts2, "tools_directory", side_effect=RuntimeError("missing backend tools")):
        result = inspect_source(tmp_path)
    assert result.backend == "sts2"
    assert not result.buildable
    assert "missing backend tools" in result.warnings


def test_sts2_no_native_host_availability_on_x86(tmp_path):
    with mock.patch.object(sts2.platform, "machine", return_value="x86_64"):
        assert not sts2.available(tmp_path)


def test_supported_sts2_routes_to_source_pipeline_with_sdk_and_permissions(tmp_path):
    source(tmp_path)
    inspection = UnifiedInspection(source_path=tmp_path, backend="sts2", engine="godot",
                                   engine_label="STS2", engine_version="4.5.1", game_name="STS2",
                                   compatibility="needs_testing", confidence="high",
                                   runtime_kind="sts2-native-source", buildable=True)
    output = tmp_path.parent / (tmp_path.name + "-converted")
    sdk = tmp_path.parent / "vendor-sdk.tar.gz"
    with mock.patch.object(sts2, "summary", return_value=inspection), \
         mock.patch.object(sts2, "build", return_value={"limitations": ["device acceptance required"]}) as build, \
         mock.patch("megcfbt.router.build_rpgm_game") as generic:
        result = build_source(tmp_path, output=output, sts2_sdk=sdk, acknowledge_licenses=True, archive=False)
    generic.assert_not_called()
    assert build.call_args.args == (tmp_path, output)
    assert build.call_args.kwargs["sdk"] == sdk
    assert build.call_args.kwargs["authorized"] is True
    assert result.launcher_path == output / "launch.sh"
    assert result.backend == "sts2"
    assert result.warnings == ("device acceptance required",)
