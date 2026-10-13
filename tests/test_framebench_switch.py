from pathlib import Path

from framebench import SWITCH_KIND
from framebench.fixtures import converted_package, fake_steam, steam_command
from framebench.switch import SwitchError, activate, looks_like_wrapper, recover, restore, wrapper_command
from framebench.wrapper import native_command, original_command, parse_steam_chain, plan, write_mode


def test_wrapper_forwards_original_percent_command_and_keeps_steam_prefix(tmp_path):
    package = converted_package(tmp_path / "stardew-frame")
    chain = steam_command()
    assert parse_steam_chain(chain, "413150")["reaper"].endswith("reaper")
    original = original_command(chain)
    assert original == chain
    native = native_command(package, chain, "413150")
    assert native[-1].endswith("launch.sh")
    assert "fex-compat-tool" not in native
    assert native[0].endswith("steam-launch-wrapper")


def test_wrapper_plan_reads_mode_file(tmp_path, monkeypatch):
    package = converted_package(tmp_path / "pkg")
    monkeypatch.setenv("FRAMEBENCH_STATE", str(tmp_path / "state"))
    write_mode(413150, "original")
    result = plan(["--package", str(package), "--appid", "413150", "--", *steam_command()])
    assert result["mode"] == "original"
    assert result["command"][-1].endswith("StardewValley")
    write_mode(413150, "native")
    result = plan(["--package", str(package), "--appid", "413150", "--", *steam_command()])
    assert result["mode"] == "native"
    assert result["command"][-1].endswith("launch.sh")


def test_transaction_restores_and_preserves_user_edits(tmp_path):
    package = converted_package(tmp_path / "pkg")
    steam = fake_steam("user -fullscreen")
    running = {"on": False}
    state = activate(
        413150, "native", package, consent=True, home=tmp_path / "home",
        steam=steam, running_check=lambda _appid: running["on"],
    )
    assert state.status == "active"
    assert looks_like_wrapper(steam.launch_options)
    assert "%command%" in steam.launch_options
    steam.launch_options = "later user edit"
    try:
        restore(home=tmp_path / "home", steam=steam, running_check=lambda _appid: False)
        raise AssertionError("should refuse to clobber a later edit")
    except SwitchError as exc:
        assert "edited" in str(exc)
    steam.launch_options = state.active_launch_options
    result = restore(home=tmp_path / "home", steam=steam, running_check=lambda _appid: False)
    assert result["restored"]
    assert steam.launch_options == "user -fullscreen"


def test_refuse_switch_while_running_and_require_consent(tmp_path):
    package = converted_package(tmp_path / "pkg")
    steam = fake_steam("")
    try:
        activate(413150, "native", package, consent=False, home=tmp_path / "home", steam=steam)
        raise AssertionError("consent")
    except SwitchError as exc:
        assert "consent" in str(exc)
    try:
        activate(
            413150, "native", package, consent=True, home=tmp_path / "home", steam=steam,
            running_check=lambda _appid: True,
        )
        raise AssertionError("running")
    except SwitchError as exc:
        assert "already running" in str(exc)


def test_crash_journal_recovers_normal_options(tmp_path):
    package = converted_package(tmp_path / "pkg")
    steam = fake_steam("")
    activate(413150, "original", package, consent=True, home=tmp_path / "home", steam=steam)
    assert steam.launch_options
    recovered = recover(home=tmp_path / "home", steam=steam, running_check=lambda _appid: False)
    assert recovered["recovered"]
    assert steam.launch_options == ""


def test_wrapper_command_does_not_point_at_steam_game_files(tmp_path):
    package = converted_package(tmp_path / "pkg")
    command = wrapper_command(package, 413150, home=tmp_path / "home")
    assert str(package) in command
    assert "steamapps/common" not in command
    assert command.endswith("%command%")
