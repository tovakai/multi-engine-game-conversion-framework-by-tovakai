# Post-extraction Steam asset deduplication

The v0.1.1.0 candidate extends the shared original-entry installer with optional
experimental asset links. **No backend is advertised as safely deduplicated until
Steam Frame gameplay and write-safety acceptance is complete.** ZIP transfer and
standalone non-Steam installation remain available without deduplication.

After choosing original-entry linking, the installer compares eligible converted
assets with the detected local Steam installation by size and SHA-256. Steam's
Linux depot is never assumed equivalent to the Windows source used in conversion.
Only byte-identical candidates are offered. Declining keeps the complete package.
Missing installations, unsupported backends, unmatched content or unavailable
read-only isolation produce zero links and zero claimed storage savings.

## Candidate backend review

| Engine family | Investigation and current policy |
| --- | --- |
| MonoGame / CelesteFrame | Audited vanilla Celeste XNA and Stardew .NET 6 profiles: only `game/Content/**/*.xnb` with an XNB header; experimental opt-in, hardware gameplay gate pending |
| Ren'Py | Loose images/audio may be static, but `.rpa` archives can include scripts and variants need their own launch contract; deferred |
| Godot | `.pck` may contain scripts, patched resources and engine-sensitive content; deferred |
| GameMaker | FORM/VM `.win` resources combine program and assets; runner behavior is not assumed read-only; deferred |
| Unity / Hollow Knight | Windows ARM64 Proton, managed replacements and depot layout need separate isolation acceptance; deferred |
| RPG Maker | Images/audio are future candidates; NW.js/plugin and mkxp-z layouts require separate write and launch contracts; deferred |

Native runtimes, executables, patched binaries/resources, launchers, scripts,
save/config files, mods and unmatched files stay in the conversion. Existing
symlinks, unsafe parent traversal and unusual source layouts are rejected.
No hardlinks are created. Multiply-linked converted files are excluded.

## Write isolation and integrity

A symlink does not protect its target. Experimental deduplication requires a
successfully tested local bubblewrap mount policy before asset replacement.
The test attempts a write to a synthetic fixture, never a Steam asset. Root is
mounted read-only; the conversion, `/tmp`, devices and existing session runtime
retain needed access. Source installation directories are overlaid read-only.
PID, networking and IPC remain shared for Steam context.

The package's standard `launch.sh` gains an integrity/isolation guard; original
contents and permissions remain in a recoverable local backup. Supported
installer workflows use that guard while deduplicated. Before every guarded
launch, local installation, symlinks, sizes and SHA-256 hashes are checked.
Updated or missing Steam assets block launching with repair guidance. Source
hashing uses Linux `O_NOATIME` and `O_NOFOLLOW`, failing closed if unavailable.

This protects supported launch paths from asset writes; it is not a hostile-code
sandbox. Do not bypass the guard by directly executing payload binaries or
manually changing links. External changes during gameplay are outside the
startup integrity check; Steam's running-game update behavior needs device
acceptance. See upstream [bubblewrap policy and limitations](https://github.com/containers/bubblewrap/blob/main/README.md).

## Transactions, space reporting and restoration

`.megcfbt/asset-links.json` records package/converter identity, profile, AppID,
source root/path, converted path, size, SHA-256, permissions, recovery paths,
timestamps and transaction states. A process lock serializes operations.
The atomic, flushed journal and guarded launcher precede asset changes. Each
converted asset is renamed to a local recovery copy before its symlink is
installed. Only a verified replacement plus durable journal permits deleting
that converted recovery copy. Originals are only read: never chmodded, renamed,
deleted or written by the installer.

The installer reports file count and measured reclaimed bytes: observed
filesystem free-space increases capped by released allocated blocks, subtracting
symlink allocation. Logical file length is not reported as actual storage
reclaimed. Delayed copy-on-write reclamation and concurrent disk activity affect
the observation; unmeasured savings are never invented.

Repeated linking validates the existing manifest without duplicate links.
Interrupted setup blocks launching and offers recovery through verify/repair.
Recovery uses an intact converted backup first; otherwise it copies only a
source matching the recorded hash. User edits are preserved. If Steam changed
or deleted the only identical source, re-extract the original conversion ZIP or
reconvert; a hash cannot reconstruct missing bytes. The ZIP is never modified.

Restoring Steam options can also restore ordinary converted asset copies.
Non-Steam registration requires asset restoration first, so standalone packages
do not depend on Steam assets or isolation. The original launcher is restored
after assets are materialized. Recovery records remain. Moved packages can
recover using relative paths, then relink at their new location.

## Acceptance evidence

Automated fixtures cover matching/modified assets, hashes, missing installs,
unsafe paths/symlinks, rejected backends, isolation failures, repeated setup,
interrupted replacement, updates/deletions and restoration. On the connected
Frame, a synthetic fixture demonstrated bubblewrap rejecting a write through a
linked asset with `EROFS`, guarded execution, restoration, and unchanged source
bytes, mode, inode, mtime, ctime and atime. This is filesystem evidence, not
real-game hardware acceptance.

Before advertising a backend as safely deduplicated:

- [ ] Test the exact game/profile on Frame with original-entry linking.
- [ ] Record identical eligible paths for Steam Linux and Windows depots.
- [ ] Test Steam Input, audio, gameplay, save and relaunch under isolation.
- [ ] Confirm source bytes and metadata stay unchanged, including attempted
      linked-asset writes and runtime asset regeneration.
- [ ] Test Steam updates/removal, secondary-library unmount, package moves,
      interruption and recovery from the retained ZIP.
- [ ] Restore copies/options; verify standalone and original Steam launching.
- [ ] Report playtime and achievements separately as verified or unverified.

These gates remain mandatory for final v0.1.1.0 publication.
