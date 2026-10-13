from framebench.catalog import discover
from framebench.fixtures import converted_package, write


def test_catalog_finds_converted_stardew_package(tmp_path):
    steam = tmp_path / ".steam" / "steam" / "steamapps"
    write(
        steam / "appmanifest_413150.acf",
        '"AppState"\n{\n"appid" "413150"\n"name" "Stardew Valley"\n"installdir" "Stardew Valley"\n}\n',
    )
    (steam / "common" / "Stardew Valley").mkdir(parents=True)
    package = converted_package(tmp_path / "devkit-game" / "Stardew_Valley")
    entries = discover(home=tmp_path, extra_packages=[package])
    match = next(item for item in entries if item.appid == 413150)
    assert match.package == package
    assert match.launcher == "launch.sh"
