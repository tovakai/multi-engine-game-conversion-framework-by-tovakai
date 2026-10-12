# UnityFrame / Hollow Knight

UnityFrame converts the exact tested Steam Windows Hollow Knight edition on
Unity `6000.0.61f1` to Windows ARM64 for ARM64 Proton on Linux/Steam Frame.
It is an experimental, title-specific profile. Other Unity editions, IL2CPP
exports and modified source assemblies are not automatically convertible.

Inspection verifies the source game assembly, Steamworks.NET wrapper, native
plugin identities and managed IL flags. It also checks the Unity version and
vanilla installation layout. A match appears as backend `unityframe`,
compatibility `needs_testing`, with Convert enabled in the GUI.

## Normal workflow

```powershell
.\.venv-win\Scripts\python.exe -m megcfbt inspect "C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight"
.\.venv-win\Scripts\python.exe -m megcfbt build "C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight" -o build/Hollow-Knight-frame
```

In the GUI, drop the original game folder and click Convert. No manual runtime
selection is required. The converter downloads and SHA-256 verifies the exact
Unity Windows ARM64 Mono support package and the pinned bs-arm64 bridge archive,
then caches them using the framework's normal runtime cache location.

For offline conversion, `--runtime DIRECTORY` or `UNITYFRAME_RUNTIME` can point
to a folder containing both original pinned archives named in
`unityframe/runtime.py`. Unverified archives fail before output is created.
`--runtime-version` cannot substitute a different Unity engine.

The converter copies the assets, replaces the player/Mono/native components,
and applies three exact-assembly input/Steam detection patches. The source is
read-only. The generated manifest inventories all twelve native ARM64 binaries
and 134 managed assemblies; the launcher verifies their hashes before play.

## Package and launch contract

The ZIP is named `*-windows-arm64-proton.zip`. Its metadata declares
`target_platform: windows-arm64-proton`, `operating_system: windows`,
`architecture: aarch64` and `runtime: arm64-proton`. Linux ELF packages retain
their existing `*-linux-aarch64.zip` naming and Steam Linux Runtime metadata.

The ordinary wrapper `launch.sh` and `install-to-steam.sh` are included.
Install ARM64 Proton 11.0 through Steam on the Frame, extract the package,
and run `./install-to-steam.sh`. Keep Steam compatibility overrides disabled
for this shell launcher. It discovers a matching installed ARM64 Proton
(`11.0-2c` or `11.0-2e`) across Steam libraries and initializes its own prefix.
`HK_ARM64_PROTON` remains an optional explicit directory override.

The prefix and saves live under `payload/.hk-arm64/compatdata` in an extracted
ZIP. The launcher's Steam bridge is configured against the selected Proton's
ARM64 Unix half, and bundled ARM64 DXVK provides Direct3D 11. Logs stay under
`payload/.hk-arm64/logs`. Live prefixes and logs are excluded when packaging a
build; the user's saves are not redistributed in the ZIP. `--force` refuses to
overwrite an output containing a prefix/saves. Fresh build outputs without a
prefix can be rebuilt using `--force` with rollback on preparation failure.

The package is about 1.2 GB compressed and 5.24 GB extracted. FrameDrop versions
with the documented 4 GiB unpacked ZIP cap need a folder transfer instead;
ordinary extraction is supported. The framework's existing transfer-size
checks still apply.

## Validation

On Steam Frame with `proton-11.0-2e-arm64`, loaded Unity/Mono/DXVK/Steam PE
modules were pure ARM64 (`0xaa64`) and the Steam Unix half was AArch64 ELF.
No FEX mappings were present in the game process. The user confirmed menu,
controller navigation, movement, jumping, audio, a bench save and successful
Continue with controller input after quit/relaunch.

See [the recorded hardware validation](../../unityframe/validation-2026-10-12.json).
The normal CLI automatic-download build and actual frozen Windows GUI drag/drop
and Convert workflow passed. The GUI-produced ZIP passed CRC and Frame binary
verification, installed its Steam shortcut and four artwork slots, and launched
through Steam using automatic Proton selection. Menu/controller navigation were
user-confirmed and the Steam-launched game again had ARM64 modules without FEX
mappings. The native binaries and patched assembly match the earlier playtested
copy byte-for-byte. The focused shared-backend regression suite passed 110 tests.
Vibration, hotplug, achievements and longer gameplay remain testing targets.
The profile remains experimental; the initial hardware result is not blanket
Unity compatibility or a performance claim.
