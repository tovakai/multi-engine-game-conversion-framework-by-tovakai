# Hollow Knight Windows ARM64 experiment

This prepares the exact audited Steam Windows edition on Unity 6000.0.61f1
for ARM64 Proton. Native startup, menu, controller movement/jumping and audio
were confirmed on Steam Frame with ARM64 Proton 11.0-2e on 2026-10-12. A bench
save, quit, relaunch and successful Continue load with working controller input
were also confirmed. Vibration, longer gameplay and Steam shortcut launch remain
unvalidated. The
recipe now runs through the normal framework build and GUI paths. Canonical code
and pinned runtime data live in `unityframe/`; these experiment scripts retain
the audit tooling and compatibility entry points. See
[normal conversion instructions](../../docs/backends/unityframe.md). The preparer creates a separate game copy;
it does not launch, install, or modify the Steam source installation.

The intended input backend is the game's existing Unity Input System manager.
Two hash-gated IL patches return false from the legacy InControl/XInput enable
getters. A third patch marks the Steam subsystem as packaged because the source
probes `Plugins/x86_64`, while this copy supplies `Plugins/ARM64/steam_api64.dll`.
Original method headers, metadata and file length are preserved. Every change
is recorded in the output manifest; mismatched or modded editions fail preflight.

The audited input fallback calls `UnityEngine.InputSystem.Gamepad.SetMotorSpeeds`
for vibration. This is static evidence, not a controller gameplay result.

## Prepare on Windows

Install the experiment's analysis/preparation dependencies into the project venv:

```powershell
.\.venv-win\Scripts\python.exe -m pip install -r experiments/hollow-knight/requirements.txt
```

Obtain the two pinned archives using the URLs in `profile.json`. Their SHA-256
hashes and extracted native-component hashes are checked before use. The script
accepts local archives and performs no automatic downloads.

```powershell
.\.venv-win\Scripts\python.exe experiments/hollow-knight/prepare.py `
  "C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight" `
  --unity-package build/UnitySetup-Windows-Mono-Support-for-Editor-6000.0.61f1.pkg `
  --bridge-package build/hollow-knight-deps/bs-arm64-v0.3.2-proton-11.0-2c.tar.gz `
  --output build/Hollow-Knight-Windows-ARM64

.\.venv-win\Scripts\python.exe experiments/hollow-knight/verify.py build/Hollow-Knight-Windows-ARM64
```

The output must not exist and must be outside the source tree. Preparation
checks the original managed assembly, Steam wrapper, plugin inventory, pure-IL
assembly flags and runtime component architectures. Downloaded archives are
read through exact allowlists. No VR/mod-loader components or x64 plugin copies
are included. Output notices preserve the selected bridge's upstream licenses,
source provenance and original Steamworks.NET notice.

## Launch on ARM64 Linux / Frame

Copy the complete prepared folder to the device, retaining its hidden
`.hk-arm64` directory. Ensure Python 3.10+ and a graphical Steam session are
available. Select an installed ARM64 Proton matching the bridge: `proton-11.0-2c`
or `proton-11.0-2e`. Initial Hollow Knight gameplay was tested on `11.0-2e`;
`11.0-2c` is accepted by the upstream bridge but has not been tested here.

```bash
HK_ARM64_PROTON="/path/to/Proton 11.0" bash ./launch-hollow-knight-arm64.sh
```

Set `HK_ARM64_STEAM_ROOT` if the Steam client is outside `~/.steam/steam`.
The launcher verifies the prepared binaries, checks the host and Proton version,
initializes its own `.hk-arm64/compatdata` prefix and links the matched Proton
Steam unix half. It selects Direct3D 11, the bundled ARM64 DXVK, and the explicit
pure-ARM64 Steam client bridge. It keeps logs under `.hk-arm64/logs` and runs the
game in the foreground. Additional game arguments follow the script name.

The source installation/prefix and existing saves are not copied or linked.
The package contains Windows ARM64 PE binaries; it is not a Linux ELF package.
Do not import it through the framework's standard Linux-native Frame metadata.

## Audit and validation

```powershell
.\.venv-win\Scripts\python.exe experiments/hollow-knight/audit.py `
  "C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight" `
  --output build/hollow-knight-audit.json
```

The audit reads all managed/native metadata, records identities, P/Invoke
libraries, native imports/exports and selected input/online method IL. Reports
are local development artifacts under ignored `build/`, not redistributed game
assemblies. The optional `steam_coverage.py` trace accepts an app-only audit:
its `external_members` seed the Steam wrapper trace, alongside callback lifecycle
methods. The initial audit covered 134 assemblies without parse errors; all had
IL-only flags without required-x86. The trace found 44 Steam exports, all present
in the pinned ARM64 bridge. Nine other bundled Steam wrapper imports are absent
from that bridge, so this is not full Steamworks API compatibility.

The device loaded ARM64 Unity/Mono/DXVK/Steam PE modules and the matching native
ARM64 Unix Steam half; the game process had no FEX mappings. Unity selected
Direct3D 11 on Turnip/Adreno 750, initialized Steam and received Steam stats.
The user confirmed the menu, controller navigation, movement, jumping, audio,
bench saving and successful Continue after quit/relaunch. Save files and backups
were observed in the dedicated prefix. See `validation-2026-10-12.json`.

These initial checks do not establish all dynamic reachability or ABI behavior. Test Steam
achievements, more gameplay/scene transitions, controller reconnection/vibration
and Steam shortcut launch on Frame. Keep the recipe experimental until that
coverage is complete.
