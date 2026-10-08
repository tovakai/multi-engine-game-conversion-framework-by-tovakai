# STS2 source-building pipeline

The four remaining release gates are tracked separately in
[RELEASE_BLOCKERS.md](RELEASE_BLOCKERS.md).

Continuation: `feat/sts2-reproducible-pipeline`, based on handoff `3747037`.
The original dirty checkout was left intact; development uses
`/tmp/sts2-converter-continuation`. Hardware experiments are confined to
`/run/media/steamos/SD512/sts2-pipeline-dev-20261008`.

This removes previously compiled game-specific extension inputs. It does **not**
claim unrestricted one-click conversion from a game installation alone: the
licensed FMOD SDK, applicable Spine permissions and an ARM64 build host remain
prerequisites. Publisher-pristine input and gameplay acceptance remain open.

## Dependency audit

| Component | Automated route | Constraint |
| --- | --- | --- |
| Godot Mono 4.5.1 | Official templates; pinned archive and member checksums | First download needs network |
| .NET ARM64 9.0.7 | Official Microsoft package; archive/member pins | First download needs network |
| Sentry Godot 1.5.0 | Official release; archive/member pins | First download needs network |
| Spine extension | Fresh exact Spine/godot-cpp checkouts and native compilation | Spine runtime integration permissions |
| FMOD extension | Fresh exact extension/godot-cpp checkouts, guarded source edits, compilation | Vendor SDK headers and libraries |
| FMOD core/studio 2.03.15 | Import original SDK ARM64 runtimes; known hashes | Closed source, authenticated vendor downloads |
| Steam API | Checksum installed Valve SteamVR ARM64 API | Exact known platform binary required |
| Game/wrapper, deps and PCK | Existing guarded original-source transformations | Only v0.98.2 / f4eeecc6 hashes accepted |

Direct Frame inspection confirmed `/opt/steamvr/bin/linuxarm64/libsteam_api.so`
matches the genuine API pin, SHA-256
`9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b`.
The pipeline never searches the prototype for dependencies. Existing Steam
patches and launch safeguards remain: no invented AppID, ownership result,
authentication result, callback, achievement or stat.

[FMOD downloads](https://www.fmod.com/download) require sign-in. Supply an
authorized original `fmodstudioapi20315linux.tar.gz` or extracted SDK. The
archive's recorded local full-file pin is not a vendor signature. Only bounded
build headers and ARM64 runtime members are imported; tar symlinks are not
extracted. Runtime and selected header pins are independently checked before
compilation. No SDK or proprietary binaries are distributed with this software.
Downloading an SDK does not grant rights; [FMOD licensing](https://www.fmod.com/licensing)
and the [Spine Runtimes license](https://esotericsoftware.com/licenses/Spine-Runtimes-License-Agreement.pdf)
apply. Game ownership is not asserted to grant Spine integration rights.
An ordinary-user release still needs an authorized vendor acquisition route
and resolution of applicable runtime integration permissions. This is an explicit
limitation, not a hidden packaging dependency.

## Usage

Build host: Linux AArch64, Python 3.10+, Git, GCC C++, readelf, SCons (tested
4.11.1). Tools may live in an isolated environment; no SteamOS system changes
are performed. Cross-compilation/remote Windows builds are not enabled yet.

```bash
python3 experiments/sts2-steamworks/preflight.py /path/to/original-game
python3 experiments/sts2-steamworks/pipeline.py \
  /path/to/original-game /path/to/new-output \
  --fmod-sdk /path/to/authorized/fmodstudioapi20315linux.tar.gz \
  --cache /path/to/separate-cache --acknowledge-licenses

python3 -m megcfbt inspect /path/to/game --json
python3 -m megcfbt build /path/to/game -o /path/to/new-output \
  --fmod-sdk /path/to/authorized/vendor-sdk --acknowledge-licenses
```

Source validation precedes downloads/builds. Unsupported v0.107.1 / 59260271 is
rejected. Each conversion compiles fresh exact source commits; native outputs
must be AArch64 ELF and export the expected extension entry points. Compiler
versions, source commits, SDK input hashes, source edits and generated hashes
are recorded in manifest-tracked `native-build.json`. Output pins for compiled
extensions derive only from the current build, without a public profile override.
Official archives are checksum-verified on every reuse.

This is a reproducible procedure, not a claim of byte-identical builds across
toolchains. Failed builds retain diagnostic logs in the cache. The existing
no-replace staging transaction never modifies original game files. Rollback
restores original Steam launch options/executable; no output or cache directories
are automatically deleted. Generated game output must not be redistributed.

STS2 detection precedes generic Godot. CLI/desktop share this backend. On an
equipped Linux AArch64 host, select the authorized SDK archive using the runtime
button, then Convert. The desktop retains the standalone permissions
acknowledgment. `MEGCFBT_STS2_FMOD_SDK` and `MEGCFBT_STS2_SCONS` configure paths.
Other hosts display unmet requirements instead of copying prepared libraries.
Wheels and desktop bundles include a software-only backend allowlist.
`convert_sts2.py` preserves the baseline; `pipeline.py` builds from source.

## Acceptance boundary

The installed Steam game is v0.107.1. The user authorized using the prior
v0.98.2 testgames tree for comparison. Its 21 selected original inputs match
all profile hashes locally; replaced Windows Steam DLL/settings are excluded.
This fixture does not prove publisher-pristine provenance.

Baseline standalone tests: 145 passed, 43 fixture skips. The framework baseline
has two pre-existing failures in `tests/test_godot_runtime_bundle.py`:
obsolete boolean assertions for a helper returning Path/None. Both were
independently reproduced from an unmodified handoff export.
Their assertions have been updated to the existing helper contract, retaining
the file-copy and missing-file checks without changing GodotSteam behavior.
Hardware and current regression results are recorded as they complete.
Native inspection/headless startup do not prove Steam ownership, graphics,
controls, audio, saves, achievements or cloud sync; those need separate
acceptance through the owned Steam library entry.

## Hardware results, 2026-10-08

These are historical results from the earlier deployed software bundle, not a
full-pipeline validation of commit `be471a9`. That commit's later SDK header-copy
loop introduced variable shadowing; the regression and its committed fix are
covered by a test that executes the complete native builder with synthetic
checkouts/compiler outputs and real verified SDK-layout writes. Fresh hardware
results for the fix will be recorded separately with the exact tested commit.

- Two independent fresh builds on the Frame reproduce both original extension
  SHA-256 hashes exactly, using GCC 15.1.1, SCons 4.11.1, Python 3.12.3 and
  binutils 2.42.0. This demonstrates equality on this toolchain, not arbitrary
  compiler reproducibility. Only the existing generic SCons tool was reused;
  no earlier game-specific extension/native output was consumed.
- The complete `pipeline.py` run used the selected original source files, the
  original vendor SDK archive, installed Valve API and checksum-verified official
  downloads. It freshly compiled its own extensions and produced an output with
  227 manifest-tracked files, all verified with correct modes on AArch64.
- Native headless execution initialized Godot 4.5.1 Mono, hostfxr/GodotPlugins,
  FMOD and both Sentry components. The genuine ARM64 Steam client loaded.
  Steam initialization failed with missing AppID because this was an SSH process,
  not an owned Steam launch. Exit code zero is **not** Steam acceptance.
  No synthetic AppID or `steam_appid.txt` was provided. User-data directories were
  isolated using XDG paths under the test workspace.
- The owned STS2 appmanifest is absent on the Frame. Manual acceptance requires
  installing/launching the owned game entry with the temporary launch option:

  ```text
  bash -c 'exec "/run/media/steamos/SD512/sts2-pipeline-dev-20261008/native-output-01/collect-startup.sh"' -- %command%
  ```

  Preserve previous launch options for rollback. Confirm Steam initialization,
  main menu, audio, controls and save/reload; achievements/cloud need separate
  evidence. Originals and SteamOS configuration have not been modified.
- Source PCK inspection found 13,158 entries and **zero embedded native library
  entries**; the pack cannot supply the missing ARM64 vendor runtimes.
- All eleven C/C++ FMOD build headers were checked against the original verified
  SDK archive. Unused C# and FSBank wrappers are excluded from the build layout.
- The optimized private-staging PCK writer uses no-replace rename, avoiding the
  second full pack write without requiring hard links. A real-pack hardware run
  produced the exact same SHA-256 as the full pipeline:
  `25e58dc52e8f5571f54b929ce5359e9057d6d7c4e6213db920f60d7ad8a2a19a`.
  The 21 original source files passed full hash verification afterward.
- Wheel build and installation into an isolated environment locate the backend
  correctly; the installed CLI rejects the actual unsupported Steam build.
- Final local regression suites: 36 framework tests passed; 156 standalone
  tests passed, 43 optional proprietary/inspection fixture tests skipped.
  The preserved five-check CLR harness was not rerun in this environment.

Raw startup logs, native inventories and complete conversion reports remain in
the isolated Frame workspace. No game, SDK, generated runtime or personal log
is committed. A sanitized hardware summary accompanies this document.
