from framebench import SCHEMA
from framebench.fixtures import add_game_process, converted_package, fake_steam, simulated_sysfs
from framebench.process import find_game_processes, snapshot_pid
from framebench.session import Session, SessionError


def test_session_refuses_unverified_mode(tmp_path):
    package = converted_package(tmp_path / "pkg")
    sys_root = simulated_sysfs(tmp_path / "sys")
    steam = fake_steam("")
    session = Session(
        413150, "native", package, consent=True, home=tmp_path / "home",
        sys_root=sys_root, steam=steam, launch=lambda appid: steam.launch_game(appid),
        running_check=lambda _appid: False, find_processes=lambda _appid: [],
        warmup_s=0, duration_s=0, interval_s=0, sleep=lambda _s: None, simulated=True,
    )
    try:
        session.run()
        raise AssertionError("unverified")
    except SessionError as exc:
        assert "does not match" in str(exc)
    assert steam.launch_options == ""


def test_session_records_simulated_native_run(tmp_path):
    package = converted_package(tmp_path / "pkg")
    sys_root = simulated_sysfs(tmp_path / "sys")
    add_game_process(sys_root / "proc", 44, machine="aarch64")
    steam = fake_steam("keep-my-link %command%")
    times = {"t": 0.0}

    def clock():
        return times["t"]

    def sleep(seconds):
        times["t"] += max(seconds, 0.25)

    session = Session(
        413150, "native", package, name="Stardew Valley", consent=True,
        home=tmp_path / "home", sys_root=sys_root, steam=steam,
        launch=lambda appid: steam.launch_game(appid),
        running_check=lambda _appid: False,
        find_processes=lambda _appid: find_game_processes(413150, sys_root / "proc"),
        clock=clock, sleep=sleep, warmup_s=0.5, duration_s=2.0, interval_s=0.5, simulated=True,
    )
    record = session.run()
    assert record.schema == SCHEMA
    assert record.simulated is True
    assert record.hardware_observed is False
    assert record.verification["matched"] is True
    assert record.metrics["system_power"]["mean"] == 6.2
    assert record.metrics["battery_discharge"]["mean"] == 6.8
    assert record.metrics["comparable_battery"] is True
    assert steam.launched == [413150]
    assert steam.launch_options == "keep-my-link %command%"
    assert snapshot_pid(44, sys_root / "proc").native_aarch64
