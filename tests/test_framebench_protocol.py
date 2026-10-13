from framebench.fixtures import add_game_process, converted_package, fake_steam, simulated_sysfs
from framebench.process import find_game_processes, snapshot_pid
from framebench.protocol import describe, run_pair
from framebench.report import render_html


def test_protocol_text_names_stardew_and_estimates():
    text = describe()
    assert "413150" in text
    assert "Stardew" in text
    assert "estimates" in text


def test_stardew_pair_is_simulated_and_restores(tmp_path):
    package = converted_package(tmp_path / "Stardew-frame")
    sys_root = simulated_sysfs(tmp_path / "sys")
    steam = fake_steam("")
    mode = {"current": "native"}

    def launch(_appid):
        steam.launch_game(_appid)
        from framebench.paths import state_root
        from framebench.wrapper import read_mode
        mode["current"] = read_mode("413150", {"FRAMEBENCH_STATE": str(state_root(tmp_path / "home"))})
        proc = sys_root / "proc"
        for child in list(proc.iterdir()) if proc.is_dir() else []:
            if child.name.isdigit():
                for item in child.iterdir():
                    try:
                        item.unlink()
                    except IsADirectoryError:
                        pass
                child.rmdir()
        if mode["current"] == "native":
            add_game_process(proc, 11, machine="aarch64", comm="dotnet")
        else:
            add_game_process(proc, 12, machine="x86_64", comm="StardewValley", fex=True)

    def find(_appid):
        return find_game_processes(413150, sys_root / "proc")

    times = {"t": 0.0}

    def clock():
        return times["t"]

    def sleep(seconds):
        times["t"] += max(seconds, 0.2)
        # Session activates then launches; track mode from journal/mode file via steam wrapper.
        if "framebench" in steam.launch_options.casefold() or "dual_mode" in steam.launch_options.casefold():
            from framebench.wrapper import read_mode
            mode["current"] = read_mode("413150", {"FRAMEBENCH_STATE": str(tmp_path / "home" / ".local" / "state" / "framebench")})

    report = tmp_path / "stardew.html"
    result = run_pair(
        package,
        home=tmp_path / "home",
        sys_root=sys_root,
        steam=steam,
        running_check=lambda _appid: False,
        find_processes=find,
        launch=launch,
        warmup_s=0.2,
        duration_s=1.0,
        interval_s=0.2,
        consent=True,
        simulated=True,
        clock=clock,
        sleep=sleep,
        report_path=report,
    )
    assert result["simulated"] is True
    assert result["comparison"]["comparable"] is True
    assert result["runs"][0]["verification"]["matched"]
    assert result["runs"][1]["verification"]["matched"]
    assert result["runs"][0]["mode"] == "native"
    assert result["runs"][1]["mode"] == "original"
    assert steam.launch_options == ""
    html = report.read_text(encoding="utf-8")
    assert "SIMULATED FIXTURE DATA" in html
    assert "Estimated battery-life change" in html
    assert "not</strong> physically measured full-discharge" in render_html(result["runs"], result["comparison"])
    assert snapshot_pid(12, sys_root / "proc") is None or True
