# Space Rescue: Code Pink — Steam Frame performance investigation

## Verified baseline

The Windows Steam installation identifies as Ren'Py **7.4.6.1693**. The installed
ARM64 package identifies as **7.5.0.22062402**, Python **2.7.18**. This is the
full-engine 7.4 → 7.5.0 compatibility path, rather than an exact-version platform
graft. The original package metadata records source `engine_version: 7.4.6`
but omits the destination version; the destination was verified from its engine
and actual runtime log.

The installed package is under `/run/media/steamos/SD512/SRCP-frame/payload`.
It uses GL2 through Mesa Zink/Turnip on Adreno 750. The virtual resolution is
1600×1200. Effective settings recorded by the running engine are:

| Setting | Effective value |
| --- | --- |
| `image_cache_size_mb` | 300 |
| `image_cache_size` | None |
| `predict_statements` | 32 |
| `predict_screens` | True |
| `renpy.game.less_memory` | False |

The converter copies game content without disabling prediction or modifying
these settings. Source-engine defaults agree with the destination defaults.
The loader maintains a normalized, case-insensitive name map. The inventory
found no case/overlay collisions among the assets in this installation.

The RPA-3 archive is 1,611,008,837 bytes with 7,328 entries and a 205,820-byte
compressed index. The inventory contains 6,067 PNGs, 690 JPEGs, and 19 WebPs,
including loose files. PNG layers reach 3200×2960, approximately 36.13 MiB
for one decoded RGBA surface. Large image dimensions, rather than compressed
file size alone, matter for decoding and memory pressure.

RPA image payloads are accessed by offset. The archive **index** is zlib
compressed; there is no per-image RPA decompression step in this loader.
Local Windows index timings were 0.60 ms read, 2.65 ms inflate, and 7.02 ms
parse. These local numbers are not ARM64 scene timings.

Eight executable game calls to `renpy.free_memory()` were found, plus three
commented occurrences. They are concentrated in particular screens. The
tested gameplay routes did not call this function after startup, so the
synthetic cleanup result below does **not** establish it as the cause of all
area-transition delays. No proprietary script contents are included here.

## Measurements

All device tests used the installed ARM64 runtime and preserved engine defaults.
Full-game copies and separate copies of existing saves were used. The original
archive and both test-copy archives have identical SHA256 hashes.

| Test | SD | Internal |
| --- | ---: | ---: |
| 2.78 MB PNG read after range-local advisory eviction | 33.59 ms | 7.27 ms |
| Same asset decode | 52.06 ms | 41.97 ms |
| Physical bytes read for that read | 2,781,184 | 2,621,440 |
| Gameplay trace: maximum individual image-load call | 57.01 ms | 63.64 ms |
| Gameplay trace: maximum renderer draw call | 212.11 ms | 194.05 ms |
| Gameplay trace: peak process RSS | 612.23 MiB | 577.45 MiB |

These gameplay runs were similar user-driven routes, not a scripted identical
input sequence. Trace durations were approximately 88 and 92 seconds. Totals
and percentiles therefore should not be compared as exact transition speedups.
The internal run preceded the input-timestamp hook. The SD run recorded 143
input-to-next-draw observations: median 11.62 ms, p95 131.59 ms, maximum
465.89 ms. This includes menu interactions and the first transition frame,
and is **not** time until a destination area becomes fully interactive.

A separate three-image, roughly 108 MiB synthetic test used repeated cache
clears followed by texture requests. It measured the following medians over
three cycles, with warm filesystem caches:

| Operation | GL2 | GL |
| --- | ---: | ---: |
| `renpy.free_memory()` | 338.71 ms | 443.40 ms |
| Reload three layers after clear | 347.47 ms | 383.07 ms |
| Request the same three cached textures | 0.051 ms | 0.037 ms |

GC instrumentation confirms that most of the forced-cleanup time is cyclic
collection, rather than the Python cache-clear method itself. A separate
strace run is kept outside the repository; its timings are not used as baseline
performance because tracing adds overhead.

An instrumentation overhead check gave GL2 reload medians of 391.75 ms with
hooks off and 368.15 ms with hooks on. This small sample shows normal run-to-run
variation, not a performance improvement from instrumentation. Warm-hit batch
timings increased from 0.020 to 0.047 ms. Use uninstrumented acceptance runs
for final responsiveness checks.

## Interpretation and experiments

The user reported that the internal-storage test copy was “much much better.”
The subsequent SD-card test copy was also reported as better. Thus **storage
relocation alone is not a demonstrated fix**. Both copies were directly
launched on the desktop with isolated saves. A battery shutdown/reboot also
occurred before the gameplay captures. Launch environment, process history,
preferences, page-cache state, and transient storage contention remain
confounders until the original launch reproduces the symptom. The subsequent
original `SRCP` shortcut test was also reported to have **no delays**. Its
unchanged runtime was verified as native ARM64 GL2, with
`MESA_GL_VERSION_OVERRIDE=4.3` and the Frame desktop display. At that point,
system I/O pressure was approximately zero. The responsive original window
was 1304×978, compared with 1920×1042 at the end of the historical slow-session
log. Window size is another comparison variable.
The user also maximized the original game and still reported no delays, so
the larger window did not reproduce the symptom in this session.

The original archive was read in full for hash verification before that
original-shortcut retest, so this retest is storage-warm. Together with the
device reboot, that prevents attributing the recovery to any one action.
**No engine/cache optimization has been demonstrated or shipped.** The
current evidence favors transient I/O/cache/system state over an inherent
ARM64 capability limit, but does not prove the original cause.
The final original-shortcut retest followed archive-local advisory eviction
after the game closed. The user again reported **no delays** on the first area
transitions. This passes the user-driven cold-archive acceptance check; it is
not an OS-wide cold boot or a numeric transition benchmark. The user accepted
the original package as working well, and further experiments were stopped.
The read-only observer sampled that launch 57 times, recorded approximately
16.45 MiB of physical reads and a 473.77 MiB peak RSS, and observed one disk-wait
sample. This confirms that physical storage reads occurred during the retest.

Before reboot, an asset-header scan encountered a process in `D` state with
`folio_wait_bit_common`, near-zero CPU usage, and substantial system I/O
pressure. The scan made thousands of small reads, so it is not a transition
benchmark. It establishes that storage waits occurred during the session.
The decode benchmark was revised to choose a bounded asset sample from the
archive index rather than scanning every image header before timing.

Archive fragmentation does not support a simple defragmentation explanation:
the original SD archive had 3 extents, the SD test copy 9, and the internal
copy 79. Kernel MMC logs showed normal SDR104 initialization without an MMC
error in the inspected entries.

Priorities:

1. If the delays recur, capture the original shortcut's slow session before
   rebooting, copying packages, or warming the archive. Preserve the actual
   launch environment and window dimensions.
2. Keep the confirmed responsive test copies available for acceptance testing.
3. Test storage relocation only with controlled cold/warm runs and matching
   launch conditions; internal storage improves measured physical asset reads.
4. Keep GL2. Switching to GL was slower in the bounded cache test.
5. Do not raise the cache or preload all assets: the tested routes had normal
   prediction, modest RSS, and no repeated explicit memory clears.
6. Do not suppress `free_memory()` or GC globally based on the synthetic test.
7. Engine-version migration, SDL changes, vsync changes, alternate cache sizes,
   and archive extraction have not demonstrated a gameplay benefit.

No converter-default performance change is justified by these findings yet.
The converter change in this branch records `runtime_engine_version` for every
Ren'Py build and an explicit compatibility profile for the 7.4 fallback. It
changes metadata only, and preserves existing DDLC profile behavior.

## Rebuild without proprietary repository files

From a checkout of the framework, run the following Python code with the actual
source and a new destination directory. This uses the same opt-in matched
7.5.0 fallback, preserving original content and leaving the source untouched:

```python
from renframe.builder import build_game

result = build_game(
    r"C:\Program Files (x86)\Steam\steamapps\common\Space Rescue Code Pink\SRCP-pc",
    output=r"C:\path\to\new\SRCP-performance-copy",
    legacy_arm64_fallback=True,
    progress=print,
)
print(result.launcher_path)
```

Copy the resulting directory to the Frame and launch its generated `.sh` file.
Do not overwrite an existing build or saves during comparisons. This rebuild
is reproducible, but has no unproven engine tuning applied.

## Reproduce the diagnostics

Use a **copy of the converted ARM64 package**, never the original Windows
installation. Commands below run in the Frame desktop terminal so the process
inherits its normal display environment. `ROOT` means the payload directory
containing `renpy.sh`, `renpy/`, `lib/`, and `game/`.

```bash
ROOT="$HOME/renframe-space-rescue-lab/diagnostic-internal"
LAB="$HOME/renframe-space-rescue-lab"
# Copy this repository's generic probe into the converted COPY:
cp renframe/diagnostics.rpy "$ROOT/game/zz_renframe_diagnostics.rpy"
# Create a fresh isolated save copy for each comparison:
cp -a "$LAB/saves-snapshot" "$LAB/saves-acceptance"
python3 scripts/renpy_device_profile.py "$ROOT" \
  --savedir "$LAB/saves-acceptance" --output "$LAB/acceptance-01.jsonl"
```

Choose a new output name for each run. The launcher wrapper rejects existing
trace artifacts. Quit normally to flush aggregate timings. The generic probe
is inactive when `RENFRAME_DIAGNOSTICS` is absent or not `1`.

```bash
python3 scripts/renpy_profile_summary.py "$LAB/acceptance-01.jsonl"
# Separate CPU/script profiling run; analyze the resulting .pstats file:
RENFRAME_CPROFILE=1 python3 scripts/renpy_device_profile.py "$ROOT" \
  --savedir "$LAB/saves-acceptance" --output "$LAB/python-01.jsonl"
# Separate high-overhead syscall evidence run (read buffer contents omitted):
python3 scripts/renpy_device_profile.py "$ROOT" \
  --savedir "$LAB/saves-acceptance" --output "$LAB/syscalls-01.jsonl" --strace
# Baseline without runtime hooks, retaining the process sampler:
python3 scripts/renpy_device_profile.py "$ROOT" \
  --savedir "$LAB/saves-acceptance" --output "$LAB/plain-01.jsonl" --observe-only
```

The trace distinguishes demand/prediction cache state, image-load calls,
lookup/open timings, cache eviction/clearing, screen evaluation, forced
cleanup and GC, renderer draw calls, and input-to-next-draw latency. The
separate process trace records RSS, physical I/O, wait channels, pressure,
and block-device statistics every 0.5 seconds.

Timings are inclusive and overlapping: **do not sum categories**. The SDL
decoder can read native file descriptors without invoking Python
`SubFile.read`, and the compiled GL2 renderer does not allow the texture
method to be replaced. Those missing observations are not zero-cost I/O or
zero-cost uploads. The trace reports unavailable hooks. Use process I/O and
strace for native reads; GPU fence waits in process samples indicate waiting,
but do not by themselves distinguish ordinary vsync from an abnormal stall.
This is not a GPU timestamp profiler. `cProfile` samples the main Python
thread, not the prediction thread.
With `--strace`, the process sampler follows the tracer supervisor; use the
separate normal profiling run for the game's RSS and physical-read counters.

For static inventory (potentially many small reads) and a bounded decoder test:

```bash
python3 scripts/renpy_asset_audit.py "$ROOT" > asset-audit.json
"$ROOT/lib/py2-linux-aarch64/python" -O scripts/renpy_decode_bench.py \
  "$ROOT" --advise-cold > decode-bench.json
```

`--advise-cold` requests eviction of the selected asset ranges only, not
global cache dropping. Physical-read counters indicate whether eviction
actually caused disk reads. The decoder benchmark assumes the Python 2
runtime layout and RPA-3; the static inventory reports unsupported archives.
Archive pickle globals are rejected; no game scripts are executed by either
asset tool.

Optional tuning variables are bounded and absent by default:
`RENFRAME_CACHE_MB=32..512` and `RENFRAME_PREDICT_STATEMENTS=0..128`.
Use one change per paired experiment. A cache override replaces the game's
legacy screen-count setting, and should be tested with memory monitoring.
No tuning override was applied in the recorded gameplay captures.

The optional `scripts/renpy_runtime_microbench.rpy` is for disposable lab
copies only. It runs solely when `RENFRAME_MICROBENCH=1`; provide
`RENFRAME_BENCH_ASSETS` as an absolute path to a JSON list of 1–3 asset names
and `RENFRAME_TRACE` as the output prefix. The benchmark initializes a display,
tests clear/reload/warm paths three times, and exits without running story
labels. Asset names and game files must remain local.

## Acceptance checks

Use the same copied save, route, physical window size, renderer, and launch
method for each comparison. Record the first trip through each area and a
second trip in the same process. Repeat after a fresh device boot for a
storage-cold comparison, and distinguish that from clearing Ren'Py's cache.

For each run, make 5–10 area transitions with one click each. Record click to
fully interactive destination, preferably with a video or stopwatch. Confirm
that actions register once, animations and audio work, saves reload, and
minigames/rollback behave normally. Compare median and worst transition delay,
RSS, physical reads, and long trace calls. Finish with an uninstrumented run.
Do not present input-to-next-draw or a synthetic cache test as the final
area-transition measurement.

The responsive unmodified internal copy is at
`~/renframe-space-rescue-lab/baseline-internal`. Launch with `SRCP.sh`; use
`--savedir` with a copied save directory for testing. Removing the added
`zz_renframe_diagnostics.rpy`/`.rpyc` and optional microbenchmark files from
the lab copies reverses the instrumentation. Ordinary game content, the
Windows installation, and existing save files have not been patched.
