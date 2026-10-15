# Versions and conversion provenance

`megcfbt/version.py:RELEASE_VERSION` is the only maintained application version.
It targets **0.1.1.0**, with non-Steam installation recommended and library
linking/deduplication explicitly experimental. v0.1.0.3 and its Git tag remain
immutable. A version number alone does not make a development build a release;
official builds require the exact matching tag, clean source and verified artifacts.
Public versions use `MAJOR.MINOR.PATCH.REVISION`; existing `0.1.0` and `0.1.0.1`
remain valid and unchanged. Python packaging uses PEP 440, including four-part
release segments, development releases and local build labels.

| Identity | Meaning |
| --- | --- |
| Git commit | Full SHA identifies committed converter source; dirty builds also record a tracked-diff SHA256 |
| Development build | Intended release + `.dev<count>+g<short-SHA>`; no manual bump or public release required |
| Public release | Deliberately chosen number; clean checkout at exactly the matching `v<version>` tag |
| Converter version | Application code that produced a conversion; independent of game/runtime versions |
| Game version | Original game's release, recorded separately when known; `null` means unavailable |
| Source engine version | Engine detected in the original game |
| Runtime engine version | Runtime selected for the converted copy, recorded when known |

The development count is `git rev-list --count HEAD` across all reachable history,
not distance from whichever tags happen to be fetched. Identical histories give
identical counts, including detached HEAD and CI merge checkouts. SHA labels
disambiguate branches with equal counts. Counts are not a global chronology across
branches. A shallow clone uses `.dev0+g<SHA>.shallow` with an explicitly unavailable
count; use `git fetch --unshallow` for a full count. CI fetches complete history.
Dirty builds append `.dirty.d<diff-digest>`. Tracked staged/unstaged changes count;
untracked files and ignored runtime caches do not. Only committed source can be
recovered from a commit SHA alone; retain the diff for a dirty conversion.

Missing Git/embedded metadata reports `dev0+unknown`, null commit/cleanliness,
and an explanatory status. This is never presented as a clean public release.
Frozen applications, wheels, source distributions and bundled STS2 tools embed
their identity during packaging; users do not need Git. Source checkouts read Git
on startup. Build times and conversion times are UTC; they do not change versions.

## Identify an old conversion

Use CLI `--version` for the existing single-line application identity and
`--build-info` for JSON, or the GUI footer's **COPY BUILD INFO** action.
Application archives contain the same identity in `BUILD.json`.

New game ZIPs include the converter version in their name, retaining their target
suffix. Read `.megcfbt/package.json` in the extracted wrapper or payload:
`conversion.converter.commit` is the full source SHA,
`conversion.converter.version` the build version, and `conversion.converted_utc`
the conversion time. Engine, runtime, compatibility profile and target fields
remain separate. Open that commit in GitHub or check it out to inspect the code.

Artwork-only repackaging preserves `conversion` and the original converter version
in the name. The archive's separate `packaging.tool`/`packaged_utc` records the tool
that refreshed the ZIP. Legacy metadata stays readable; repackaging a legacy build
keeps its unversioned name and never invents original conversion provenance.
Existing archives require `--force`; explicit archive names remain supported by
the packaging API. Source game installations are not versioned or modified.

STS2 keeps its two stages and independent game `release`/`commit` fields.
`frame-package.json:preparation` and the prepared game manifest's `conversion`
record PC preparation. The game conversion manifest's `finalization` and
`installation-result.json` record device finalization, including execution
architecture and time. Bundled backend identity travels with the sealed handoff;
it is not replaced by an unrelated converter installed on the device. Preparation
ZIP names include `-prep-conv-v<version>-linux-aarch64.zip`; explicit pipeline TAR
names remain caller-controlled. Old handoffs without provenance remain supported.

See [release process](release-process.md) for preparing a public release.
