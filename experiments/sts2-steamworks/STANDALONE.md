# STS2 standalone ARM64 converter: first acceptance run

The continuation adds the source-building backend `pipeline.py`. See
[SOURCE_PIPELINE.md](SOURCE_PIPELINE.md) for framework integration, requirements
and remaining vendor/source/device acceptance limitations. The procedure below
retains the supplied-native baseline for comparison.

## Scope

This is the first complete **locally tested** standalone pipeline, isolated from
GodotFrame's normal backends. Actual clean-installation conversion and Frame
acceptance are still pending. Only the exact observed Windows **v0.98.2 /
f4eeecc6** required files are supported; v0.107.1 is deliberately refused.

Use a legitimate installation you own. Its directory is an argument, never a
hardcoded personal path. Hash recognition is not publisher authenticity or a
license grant. The observed tree had an unverified Windows Steam replacement
and settings: none of those, Windows executables, backups, saves, or unselected
files are copied. The observed managed game contains NullAchievementStrategy;
this converter does not add or remove it, and achievement support is unproven.
If your legitimate v0.98.2 files differ, retain the refusal report rather than
changing hashes or using a different unofficial installation.

The five native files below must be explicitly supplied and authorized. Their
complete sizes, SHA-256 hashes and destination mappings are fixed in
`converter_profile_v1.json`. No proprietary binaries are distributed with the
converter. You can supply matching files from any authorized location, not
necessarily the prototype. Preserve applicable FMOD, Spine, Steam and other
dependency permissions; the acknowledgement switch is not permission itself.

Required host: Python 3.10+ on Windows or Linux; standard library only. No Godot
editor, .NET SDK, native compiler, Mono, inspection modules or SDK build is
needed. Allow about **7 GiB of additional free space** for the official archives,
staged output and optional uncompressed transfer archive. Existing outputs are
never overwritten. Download and conversion can be rerun with a new output path.

## Decisions

- The verified managed chain is retained: ARM64 metadata on the exact game and
  wrapper, genuine generic interface accessors, SteamClient023, UserStats013,
  and real `GetStat("architect_damage", out int)` readiness. No fake callbacks.
- The 14 other game-managed assemblies and runtimeconfig are copied unchanged.
  All 186 runtime deployment files come from official ARM64 .NET 9.0.7; Godot
  and Sentry binaries come from their pinned official releases.
  Pinned Godot/Sentry/Spine license texts, Godot third-party copyrights, .NET
  license/notices and the converter AGPL are preserved under output `licenses`.
  These do not grant FMOD/Spine rights or certify all native/game obligations.
- Only the two packed FMOD/Sentry manifests and the pack directory pointer are
  adapted. Original asset payload bytes/offsets and the Spine manifest remain.
  Original game code outside the verified managed patches remains unchanged.
- Dependency metadata uses `observed`, the semantically verified working
  prototype graph, including its residual Windows RID fallback. The separately
  tested corrected fallback is deferred until hardware acceptance of this path.
- X11 is the default, matching the successful prototype launch. Display/session
  variables are inherited from Steam; no SSH-specific display path is forced.
- The launcher requires AppID 2868840 from Steam and does not manufacture AppID,
  ownership, authentication or achievement success. The game still performs its
  genuine Steam initialization. The launcher environment check is not a license
  check and is not presented as one.
- Private staging avoids a hard-link requirement. Final publication uses
  Windows no-replace rename or Linux `renameat2(RENAME_NOREPLACE)`; unsupported
  hosts/filesystems fail safely. No cross-input writes or in-place rollback is
  needed. Interrupted conversion may leave a hidden `.sts2-conversion-*` staging
  directory, but not a published successful result. Power-loss durability is
  not guaranteed.
- The optional tar is deliberately uncompressed: the pack is already large and
  compression would add latency. Linux execute modes are stored even when the
  converter runs on Windows. An archive failure can leave a completed, valid
  output directory; the JSON report states this rather than deleting it.
- Native rebuilds, backend/GUI wiring, other game releases, `dxgi.dll` logging
  and extra controller changes are outside this acceptance milestone.

## One Consolidated Procedure

These are preparation and one game acceptance run, not incremental diagnostics.
Run the Windows block from the extracted `sts2-converter` directory (or this
experiment directory in the checkout). Replace `FRAME_HOST`; select your clean
installation when prompted. The five SCP requests use recovered build/SDK
locations, with **only** the explicitly supplied Steam API taken from its known
deployed location. No game, pack, managed assemblies or launcher are retrieved
from the prototype. Alternatives can be placed in `native` with the same five
basenames before conversion; the converter still enforces the same full hashes.

### 1. On Your Windows Computer, PowerShell

```powershell
$ErrorActionPreference = 'Stop'
$Frame = 'steamos@FRAME_HOST'
$Source = Read-Host 'Full path of your clean, legitimate STS2 v0.98.2 game directory'
$Work = Join-Path $PWD 'sts2-acceptance-01'
if (Test-Path -LiteralPath $Work) { throw 'Choose a new Work directory; existing work will not be overwritten.' }
New-Item -ItemType Directory -Path $Work | Out-Null
$Native = Join-Path $Work 'native'
$Cache = Join-Path $Work 'runtime-cache'
$Output = Join-Path $Work 'output'
$Tar = Join-Path $Work 'sts2-arm64.tar'
New-Item -ItemType Directory -Path $Native | Out-Null
$Transfers = @(
  @('/run/media/steamos/SD512/spine-arm64-build/spine-runtimes/spine-godot/bin/linux/libspine_godot.linux.template_release.arm64.so', 'libspine_godot.linux.template_release.arm64.so'),
  @('/run/media/steamos/SD512/fmod-arm64-build/fmod-gdextension/demo/addons/fmod/libs/linux/libGodotFmod.linux.template_release.arm64.so', 'libGodotFmod.linux.template_release.arm64.so'),
  @('/run/media/steamos/SD512/fmod-arm64-build/sdk-layout/linux/core/lib/arm64/libfmod.so.14', 'libfmod.so.14'),
  @('/run/media/steamos/SD512/fmod-arm64-build/sdk-layout/linux/studio/lib/arm64/libfmodstudio.so.14', 'libfmodstudio.so.14'),
  @('/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/libsteam_api64.so', 'libsteam_api64.so')
)
foreach ($Item in $Transfers) {
  scp -- "${Frame}:$($Item[0])" (Join-Path $Native $Item[1])
  if ($LASTEXITCODE -ne 0) { throw "Dependency transfer failed: $($Item[1])" }
}
python .\fetch_converter_runtimes.py $Cache | Tee-Object -FilePath (Join-Path $Work 'downloads.json')
if ($LASTEXITCODE -ne 0) { throw 'Official artifact download/checksum verification failed.' }
python .\convert_sts2.py $Source $Output `
  --native-dir $Native `
  --godot-templates (Join-Path $Cache 'Godot_v4.5.1-stable_mono_export_templates.tpz') `
  --dotnet-runtime (Join-Path $Cache 'microsoft.netcore.app.runtime.linux-arm64.9.0.7.nupkg') `
  --sentry-archive (Join-Path $Cache 'sentry-godot-1.5.0+6c4d74e.zip') `
  --acknowledge-licenses --tar $Tar | Tee-Object -FilePath (Join-Path $Work 'conversion.json')
if ($LASTEXITCODE -ne 0) { throw 'Conversion refused/failed. Keep conversion.json; do not alter expected hashes.' }
python (Join-Path $Output 'verify_output.py') $Output
if ($LASTEXITCODE -ne 0) { throw 'Final local output validation failed.' }
Get-FileHash -LiteralPath $Tar -Algorithm SHA256
ssh -- $Frame 'mkdir -- "$HOME/sts2-arm64-transfer-01"'
if ($LASTEXITCODE -ne 0) { throw 'Choose a new remote transfer directory; an existing one is never reused.' }
scp -- $Tar "${Frame}:~/sts2-arm64-transfer-01/sts2-arm64.tar"
if ($LASTEXITCODE -ne 0) { throw 'Output transfer failed.' }
```

The remote transfer directory is also exclusively new; use a different
acceptance number for a retry. To use existing official downloads, omit the downloader and
pass their paths to the three archive arguments. Full verification still runs.
Downloads are HTTPS with pinned archive and member SHA-256 checks, with no
verification bypass. Cached archives are verified, never blindly trusted.

### 2. In Your Existing Frame SSH Terminal, Bash

Compare the printed archive SHA with the Windows value before extraction.
The extraction uses a new directory and an exclusive file mode, not overwriting
tar extraction. It also restores Linux modes on filesystems that support them.
On a filesystem mounted `noexec`, select a different execution-capable volume;
no permissions or mount options are changed by this procedure.

```bash
sha256sum "$HOME/sts2-arm64-transfer-01/sts2-arm64.tar"
python3 - <<'PY'
import os
from pathlib import Path, PurePosixPath
import tarfile

archive = Path.home() / 'sts2-arm64-transfer-01/sts2-arm64.tar'
destination = Path('/run/media/steamos/SD512/sts2-clean-acceptance-01')
if any(p.is_symlink() for p in (destination, *destination.parents, archive)):
    raise SystemExit('Symbolic link refused')
with tarfile.open(archive, 'r:') as package:
    members = package.getmembers()
    seen = set()
    for item in members:
        path = PurePosixPath(item.name)
        if (not item.isfile() or not item.name.startswith('sts2-arm64/')
                or path.is_absolute() or '..' in path.parts or '\\' in item.name
                or ':' in item.name or path.as_posix() != item.name or item.name in seen):
            raise SystemExit('Unsafe or duplicate transfer member')
        seen.add(item.name)
    destination.mkdir()  # Fails if the destination already exists.
    for item in members:
        target = destination.joinpath(*PurePosixPath(item.name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with package.extractfile(item) as source, target.open('xb') as output:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
        os.chmod(target, item.mode & 0o777)
print(destination / 'sts2-arm64')
PY
python3 /run/media/steamos/SD512/sts2-clean-acceptance-01/sts2-arm64/verify_output.py --check-modes
```

Proceed only with `errors: []`. Compare `manifest_sha256` with the conversion
JSON from Windows. Verification is static, not a signed authenticity guarantee.
If extraction/verification fails, stop and preserve its output and the original
conversion JSON; no game launch is necessary to diagnose a bad transfer.

### 3. One Launch Through The Real Owned Steam Game Entry

Record the existing Slay the Spire 2 launch options first. In Steam properties
for **Slay the Spire 2, AppID 2868840**, temporarily replace them with:

```text
bash -c 'exec "/run/media/steamos/SD512/sts2-clean-acceptance-01/sts2-arm64/collect-startup.sh"' -- %command%
```

This replaces the executable command while retaining the real Steam launch
context; the original command is passed as unused positional arguments to
`bash`, not to the ARM64 game. Do not use a non-Steam shortcut or override
`SteamAppId` to pass the launcher check. Do not edit the original game files.
Launch the owned game normally from the Frame UI. Preserve your original Steam
compatibility setting for rollback; this wrapper itself runs native ARM64,
not the original Windows executable or Proton command.

For this acceptance run:

1. Confirm `Steamworks initialization succeeded!`, no startup failure/dialog,
   and access to the main menu. Exit code zero alone is not a pass.
2. Start a short run and test animation, music/audio, mouse, gamepad and Frame
   Confirm/Cancel/navigation/Settings controls; note exactly which fail.
3. Save/exit normally, then launch once more through the same entry and reload.
   Record observed save/reload behavior. The game may write genuine local/Steam
   user data during play; back up personal saves using your normal process first.
4. Report Steam connectivity and any stats/achievement/cloud evidence you
   actually observe. Do not force achievements or infer cloud synchronization
   from successful remote-storage writes. These are separate validation claims.

If native launch is never reached and no diagnostic files appear, collect the
Steam launch error shown by the UI. Do not start changing DLLs or controller
patches. Restore the original Steam launch options to roll back; the original
installation and manually assembled prototype have not been changed.

### 4. Collect The Result Once, Success Or Failure

```bash
ROOT=/run/media/steamos/SD512/sts2-clean-acceptance-01/sts2-arm64
printf 'Diagnostic files:\n'
find "$ROOT/diagnostics" -maxdepth 1 -type f -printf '%f\n'
python3 "$ROOT/verify_output.py" --check-modes
```

On Windows, after the run has exited:

```powershell
scp -r -- "${Frame}:/run/media/steamos/SD512/sts2-clean-acceptance-01/sts2-arm64/diagnostics" $Work
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic transfer failed; report whether the directory exists.' }
```

Return `conversion.json`, the latest diagnostic JSON and verbose game log, and
your four acceptance observations. Logs may contain Steam IDs or other personal
details: review/redact before public sharing. Do not upload saves, account
credentials, SDK contents, the converted tar, or game binaries. The diagnostic
collector records file integrity, ARM64 host architecture, native `NEEDED` /
`RPATH` / `RUNPATH` / `SONAME` entries via `readelf` if available, AppID/GameID,
display-variable presence and Steam client presence. It never calls Steam or
uses `ldd`, and does not dump the full environment. The game log captures the
actual startup exception and game exit code. Known `dxgi.dll` debug logging
remains deferred unless it prevents this run.

## Local Evidence

Final isolated suite: **196 passed, no skips** with all local optional fixtures
and official archives supplied. No actual Steam Frame run was performed here.

Synthetic end-to-end tests cover the exact deployment file plan, original-source
preservation, exclusion of unrelated/Windows files, original-hash refusals,
wrong architectures, archive member/duplicate/symlink/traversal guards, private
staging cleanup, destination publication races, tar hash/mode round-trip, JSON
CLI behavior, shell syntax and launch-context safeguards. Official x86-64 Godot
independently reads the pack produced by the complete synthetic converter.

A separate integration test runs the real inspected managed recipes and original
deps through this pipeline, extracts the checksum-verified official Godot,
.NET and Sentry archives, and uses the genuine Steam API input. The other four
supplied native binaries, unchanged game dependency DLLs and full 1.6 GiB game
pack are not available locally, so their stand-ins are explicitly synthetic in
that integration test. Existing actual packed-manifest and typed CLR recipe
tests supply additional focused evidence; none is actual ARM64 device execution.
A relocated software bundle also executes the real CLI with site packages
disabled and the actual observed packed manifests; only its temporary test
profile pins identify the unavailable synthetic inputs. Production hashes are
never overridden by a CLI option.
