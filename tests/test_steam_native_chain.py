import os
from pathlib import Path

import pytest

from megcfbt import steam_library as lib


def elf(path, machine=183):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(20)
    header[:6] = b'\x7fELF\x02\x01'
    header[18:20] = machine.to_bytes(2, 'little')
    path.write_bytes(header)
    path.chmod(0o755)


@pytest.fixture
def chain(tmp_path):
    steam = tmp_path / 'Steam'
    wrapper, reaper = steam / 'linuxarm64/steam-launch-wrapper', steam / 'steamrtarm64/reaper'
    elf(wrapper)
    elf(reaper)
    tools = steam / 'steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin'
    elf(tools / 'pressure-vessel-wrap')
    runtime = tools / 'pressure-vessel-unruntime'
    runtime.write_text('#!/bin/sh\nexit 0\n')
    runtime.chmod(0o755)
    root = tmp_path / 'Converted game'
    (root / '.megcfbt').mkdir(parents=True)
    (root / '.megcfbt/steam_library.py').write_text('# synthetic helper')
    args = [str(wrapper), '--oom-score-adjust', '900', '--', str(reaper), 'SteamLaunch',
            'AppId=413150', '--', '/Steam/FEX-Emu/fex-compat-tool', 'waitforexitandrun',
            '/Steam/SteamLinuxRuntime_soldier/start', '--', '/Original/StardewValley']
    return root, steam, runtime, args


def test_native_chain_keeps_frame_harness_and_replaces_foreign_suffix(chain):
    root, steam, runtime, args = chain
    command = lib.native_launch_plan(root, 413150, args, steam_directories=[steam])
    assert command[:8] == args[:8]
    assert command[8] == str(runtime)
    assert '--no-copy-runtime' in command and '--no-gc-runtimes' in command
    assert '--run-converted' in command
    assert '/Steam/FEX-Emu/fex-compat-tool' not in command
    assert '/Original/StardewValley' not in command
    assert not any('Proton' in arg for arg in command)


@pytest.mark.parametrize('change', ['appid', 'wrapper', 'reaper', 'options', 'x86', 'missing', 'unexpanded'])
def test_unsafe_or_unsupported_native_chain_fails_closed(chain, change):
    root, steam, runtime, args = chain
    if change == 'appid':
        args[6] = 'AppId=999'
    elif change == 'wrapper':
        alternate = steam / 'untrusted-wrapper'
        elf(alternate)
        args[0] = str(alternate)
    elif change == 'reaper':
        alternate = steam / 'untrusted-reaper'
        elf(alternate)
        args[4] = str(alternate)
    elif change == 'options':
        args[1] = '--arbitrary-command'
    elif change == 'x86':
        elf(runtime.with_name('pressure-vessel-wrap'), 62)
    elif change == 'missing':
        runtime.unlink()
    else:
        args = ['%command%']
    with pytest.raises(ValueError):
        lib.native_launch_plan(root, 413150, args, steam_directories=[steam])


def test_arm64_host_runtime_in_secondary_library(chain, tmp_path):
    root, steam, runtime, args = chain
    library = tmp_path / 'mounted SD'
    destination = library / 'steamapps/common/SteamLinuxRuntime_4'
    destination.parent.mkdir(parents=True)
    runtime.parents[2].rename(destination)
    path = str(library).replace('\\', '\\\\')
    (steam / 'steamapps/libraryfolders.vdf').write_text(
        f'"libraryfolders" {{ "1" {{ "path" "{path}" }} }}')
    command = lib.native_launch_plan(root, 413150, args, steam_directories=[steam])
    assert str(destination / 'pressure-vessel-arm64/bin/pressure-vessel-unruntime') in command
