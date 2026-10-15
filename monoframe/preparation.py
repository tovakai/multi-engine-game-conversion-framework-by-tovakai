"""Choose a native host preparer separately from the ARM64 game runtime."""
from pathlib import Path
import platform
import shutil
import sys
from megcfbt.native_backend import NativeBuildError
from rpgmframe.elf import read_elf_architecture


def preparation_command(sdk, tool):
    if sys.platform == 'win32':
        return [str(sdk / 'prepare/windows-x64' / (tool + '.exe'))]
    if not sys.platform.startswith('linux'):
        raise NativeBuildError('MonoFrame preparation supports Windows and native Linux hosts.')
    architecture = platform.machine().lower()
    if architecture in {'aarch64', 'arm64'}:
        executable = sdk / 'dotnet/dotnet'
    elif architecture in {'x86_64', 'amd64'}:
        host = shutil.which('dotnet')
        executable = Path(host).resolve() if host else None
        if executable is None or read_elf_architecture(executable) != 'x86_64':
            raise NativeBuildError('Linux x64 MonoFrame preparation needs a native x64 .NET host on PATH with the runtime required by the SDK preparer. Install the matching Microsoft .NET runtime, then retry; the packaged ARM64 dotnet is only for Frame.')
    else:
        raise NativeBuildError(f'Unsupported MonoFrame preparation host architecture: {architecture}')
    return [str(executable), str(sdk / 'prepare/managed' / (tool + '.dll'))]
