from framebench.fixtures import add_game_process
from framebench.process import find_game_processes, game_is_running, verify_mode


def test_native_and_fex_processes_are_distinguished(tmp_path):
    proc = tmp_path / "proc"
    add_game_process(proc, 101, machine="aarch64", comm="dotnet")
    native = find_game_processes(413150, proc)
    assert native and native[0].native_aarch64
    assert verify_mode("native", native).matched
    assert not verify_mode("original", native).matched

    add_game_process(proc, 202, machine="x86_64", comm="StardewValley", fex=True)
    both = find_game_processes(413150, proc)
    fex = [item for item in both if item.fex]
    assert fex
    assert verify_mode("original", fex).matched
    assert not verify_mode("native", fex).matched
    assert game_is_running(413150, proc)


def test_missing_process_is_unverified(tmp_path):
    result = verify_mode("native", [])
    assert result.matched is False
    assert "No Steam-owned" in result.reason
