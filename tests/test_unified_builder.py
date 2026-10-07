from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from multi_engine_game_conversion_framework_by_tovakai import builder
from multi_engine_game_conversion_framework_by_tovakai.models import (
    Backend,
    UnifiedInspection,
)


def _renpy_inspection(source: Path) -> UnifiedInspection:
    return UnifiedInspection(
        source_path=source,
        recognized=True,
        backend=Backend.RENPY,
        family="renpy",
        engine="Ren'Py",
        engine_version="8.3.4",
        game_name="Fixture",
        confidence="high",
        compatibility="likely_compatible",
    )


def test_renpy_build_uses_working_copy_and_preserves_runtime_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Fixture"
    (source / "game").mkdir(parents=True)
    marker = source / "game" / "marker.txt"
    marker.write_text("original", encoding="utf-8")

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    expected_zip = output_dir / "Fixture-linux-aarch64.zip"
    expected_zip.write_bytes(b"old output")

    monkeypatch.setattr(builder, "inspect_source", lambda _source: _renpy_inspection(source))

    observed = {}

    def fake_convert(conversion_source, **kwargs):
        conversion_source = Path(conversion_source)
        observed["source"] = conversion_source
        observed["force"] = kwargs["force"]
        (conversion_source / "game" / "marker.txt").write_text("mutated", encoding="utf-8")
        Path(kwargs["output_zip"]).write_bytes(b"new output")
        return SimpleNamespace(
            version="8.3.4",
            game_name="Fixture",
            archive_path=Path(kwargs["output_zip"]),
            messages=[],
        )

    monkeypatch.setattr(builder, "convert_renpy", fake_convert)

    result = builder.build_game(
        source,
        output_dir=output_dir,
        force=True,
    )

    assert observed["source"] != source
    assert observed["force"] is False
    assert marker.read_text(encoding="utf-8") == "original"
    assert expected_zip.read_bytes() == b"new output"
    assert result.archive_path == expected_zip
    assert result.output_path == expected_zip
