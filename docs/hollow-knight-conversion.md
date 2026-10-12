# Hollow Knight conversion development

Status: inspection and an isolated experimental preparer implemented, 2026-10-12.
A copied Windows ARM64 candidate was prepared, verified and launched on Steam
Frame. Menu, controller navigation, gameplay movement/jumping and audio are
user-confirmed. Bench saving, quit/relaunch and Continue load with working
controller input are also confirmed. Further compatibility coverage is pending;
the exact tested edition now uses the standard CLI/GUI build flow through
[UnityFrame](backends/unityframe.md). Other Unity exports remain gated. See the
[experiment instructions](../experiments/hollow-knight/README.md) and
[recorded validation](../experiments/hollow-knight/validation-2026-10-12.json).

## Installed source

Read-only inspection of the owner's Steam Windows installation found Unity
`6000.0.61f1`, 134 managed DLLs including `Assembly-CSharp.dll`, and no root
`GameAssembly.dll`. This is a Mono candidate. The engine and all three bundled
native plugins are PE x64:

| Component | Work required |
| --- | --- |
| UnityPlayer / executable / MonoBleedingEdge | Exact-version official player extracted and verified as pure ARM64; per-file SHA-256 pins recorded. |
| InControlNative.dll | Twelve native entry points audited. Experiment disables this backend through an exact-assembly patch and selects the game's Unity Input System fallback. |
| XInputInterface64.dll | State/vibration entry points audited. Experiment disables this legacy backend through an exact-assembly patch; the Unity fallback handles controller/vibration calls. |
| steam_api64.dll | Pinned bs-arm64 bridge covers all 44 statically traced exports; Steam initialization and stats retrieval worked on Frame. Achievements need testing. |

The source installation has not been modified or executed; tests run a separate
prepared copy. All 134 managed
assemblies were audited without parse errors and have IL-only flags without
required-x86. Static analysis is not an exhaustive dependency analysis;
dynamically loaded libraries and actual runtime reachability still need testing.

## Intended conversion route

Prepare a separate copy using a matching **Windows ARM64 Mono Unity player under
ARM64 Proton** on Frame. This is a different output contract from the framework's
Linux ELF packages. Preserve the Windows shader/data route initially.

[bs-arm64's architecture](https://github.com/DaVarga/bs-arm64/blob/master/docs/ARCHITECTURE.md)
provides a working reference for selected Beat Saber editions: matching Unity
player replacement, ARM64 native bridges and Proton integration. Its success
does not establish Hollow Knight compatibility. Pin upstream commits and review
licensing before importing code. The bridge's Steam interface coverage must be
checked against this installation; do not assume a newer SDK is ABI compatible.

The [official Unity release API](https://services.api.unity.com/unity/editor/release/v1/releases?version=6000.0.61f1)
was queried during this investigation and identifies revision `74a0adb02c31`.
Its `windows-mono` module for macOS/Linux references
[UnitySetup-Windows-Mono-Support-for-Editor-6000.0.61f1.pkg](https://download.unity3d.com/download_unity/74a0adb02c31/MacEditorTargetInstaller/UnitySetup-Windows-Mono-Support-for-Editor-6000.0.61f1.pkg),
309,040,054 bytes, with published MD5 `c209e3a5bb7df40d94db8cee313333bb`.
The archive was downloaded and its published MD5 matched. Its locally verified
SHA-256 is `790faec049f2980779622cf6476d6d16d15b3d861ba4bed67c7cfc823f1e5388`.
The `win_arm64_player_nondevelopment_mono` variation supplies `WindowsPlayer.exe`,
`UnityPlayer.dll`, `UnityCrashHandler64.exe` and `mono-2.0-bdwgc.dll`; all four
have PE machine `0xaa64`. Component SHA-256 pins are in the experiment profile.
The raw response is retained locally under `build/hollow-knight-unity-release.json`.
The extractor uses an exact allowlist, validates payload bounds and gzip CRC,
and rejects duplicate or nonregular selected entries.

## Implemented foundation

`megcfbt/unity.py` now supplies the normal CLI/GUI inspection path with bounded
engine-version reads, scripting-backend evidence and recursive native-plugin
inventory. PE machine values distinguish ARM64, ARM64EC and ARM64X. Unknown,
ambiguous and IL2CPP inputs remain gated. Hollow Knight's exact observed layout
is identified as a research candidate, not a supported build profile.

```powershell
.\.venv-win\Scripts\python.exe -m megcfbt inspect "C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight" --json
```

Unmatched Unity inputs retain the unsupported-input exit code. The exact tested
edition routes to `unityframe`, enables Convert and uses automatic verified
runtime downloads. No runtime download is triggered by inspection. The canonical
`unityframe/prepare.py` prepares only
the exact audited source assembly/wrapper/plugin identities from local pinned
archives. It verifies all native output binaries as pure ARM64 and all copied
managed binaries as IL-only. It preserves source notices and upstream bridge
licenses/provenance, applies three reviewed tiny-method patches and writes a
manifest. Original assets are copied; no reconstructed project is exported.

The initial prepared copy contains twelve ARM64 native components and 134
managed assemblies. The launcher uses a dedicated prefix and validates binary
hashes before launch. The output is explicitly `windows-arm64-proton`, not a
Linux ELF package. Shared packaging now preserves this target contract, supplies
the ordinary Steam installer and excludes live prefixes/logs. The target launcher
automatically discovers supported installed ARM64 Proton versions.

Read-only process inspection on Frame verified loaded Unity, Mono, DXVK and
Steam PE modules as machine `0xaa64`, plus the Proton Steam Unix half as ELF
AArch64 (`183`). No FEX mappings were present in the game process. Unity logged
Direct3D 11 on Turnip/Adreno 750, successful Steam initialization and stats
retrieval. The user confirmed a visible menu, controller navigation, movement,
jumping and audio. After a bench save and quit, the same copy was relaunched and
Continue loaded the saved character with working controller input. The save and
backup/versioned files were observed in the dedicated prefix. SHA-256 comparison
verified 1,757 retained source data files
match the copied files; only the selected managed assembly and native components
are intentionally replaced. Logs and full process evidence remain local under
ignored `build/`.

The Steam trace traversed 154 wrapper methods, including callback lifecycle
seeds, and found 44 bridge exports without missing symbols or parse errors.
Across the entire bundled Steam wrapper, nine other imports are absent from
the bridge; none appeared in this trace. This is not full Steamworks API or
ABI compatibility. The game also explicitly probes `Plugins/x86_64` to select
its Steam subsystem. The exact-edition preparation patch marks that subsystem
as packaged only in the copied candidate that supplies the ARM64 bridge.

## Next implementation gates

1. Continue Frame tests for controller vibration, gameplay transitions,
   extended save/load coverage, achievements and Steam shortcut launch. Protect existing saves during
   tests. Keep compatibility experimental until those results are recorded.
2. Validate controller hotplug/reconnection and the selected Unity input backend
   under the pinned Proton versions. Confirm Galaxy/GameCore paths remain inactive
   for the exact Steam edition and audit any dynamically requested dependencies.
3. Record broader performance/compatibility results. The GUI-generated package
   has now installed and launched its Steam shortcut with automatic Proton
   selection; menu/controller navigation were user-confirmed. Keep Linux ELF validation separate from
   the Windows ARM64 Proton package contract.

Tests additionally cover allowlisted extraction, duplicate/link rejection,
missing/truncated packages, gzip CRC failures, exact-assembly patch refusal,
source/output separation, bridge traversal rejection and target-side ARM64EC
rejection. Launcher shell syntax and the prepared binary inventory were checked
locally. The separate hardware/user evidence above establishes initial startup
and gameplay, rather than relying on those static checks alone.
