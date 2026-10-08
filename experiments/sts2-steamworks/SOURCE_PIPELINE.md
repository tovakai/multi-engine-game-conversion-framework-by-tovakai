# STS2 source-building pipeline

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
Hardware and current regression results are recorded as they complete.
Native inspection/headless startup do not prove Steam ownership, graphics,
controls, audio, saves, achievements or cloud sync; those need separate
acceptance through the owned Steam library entry.
