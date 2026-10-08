# Fresh Frame validation of the SDK-loop fix

Tested runtime source commit: **49d5a88a0fb33cb20ad19a4a2550d32448fad3f0**.
This is a fresh complete conversion, not a rerun of the earlier deployed bundle.
The following evidence/CI commit changes no runtime Python code or profiles.
See [hardware_validation_49d5a88.json](hardware_validation_49d5a88.json) for
machine-readable results and [RELEASE_BLOCKERS.md](RELEASE_BLOCKERS.md) for the
four independent unfinished release gates.

## Regression and tests

`be471a9` reused `name` for the FMOD basename and each SDK header path, so its
runtime lookup used a header path. The fix separates `library_stem`,
`header_path` and `header_bytes`.

The new regression test executes `build_native.build` through verified inputs,
real core/studio SDK layout writes, both compiler invocations, extension checks,
generated profile and evidence publication. Checkout, compilation and external
tool output are synthetic; all library/header layout bytes are checked. The
same test fails on `be471a9` with
`KeyError: api/studio/inc/fmod_studio.hpp.so.14` and passes on the fix.
The standalone suite is now included in the GitHub test workflow.

Local suites: **36 framework tests passed**, **157 standalone tests passed /
43 fixture skips**. The Frame independently ran the committed standalone suite:
**200 tests, 43 skipped, no failures**. The five-check CLR harness was not rerun.

## Exact committed source and public framework entry point

The fix was committed before deployment. Its `git archive HEAD` SHA-256 was
verified on the Frame before extraction:
`993b92fa766431a6d14dd9265cc65e60fcefc283e5dcbb7d98a2a35ae979ea29`.
After conversion, the runner checked the archive's Git commit header and all
**160 committed regular files** against the deployed snapshot.

From that checkout, the public framework CLI ran:

```bash
MEGCFBT_STS2_FMOD_SDK=/home/steamos/Downloads/fmodstudioapi20315linux.tar.gz \
MEGCFBT_STS2_SCONS=/run/media/steamos/SD512/spine-arm64-build/.venv/bin/scons \
python3 -m megcfbt build \
  /run/media/steamos/SD512/sts2-pipeline-dev-20261008/source \
  --output /run/media/steamos/SD512/sts2-regression-validation-01/native-output \
  --fmod-sdk /home/steamos/Downloads/fmodstudioapi20315linux.tar.gz \
  --acknowledge-licenses --no-archive
```

It exited **0** after the complete source verification, vendor SDK import,
fresh pinned source fetches, native compilation, official runtime acquisition,
managed/deps/PCK transformations, static validation and new-directory publication.
Only a generic SCons executable was reused, not earlier game-specific binaries.

Both fresh extension hashes match the working references:

| Extension | SHA-256 |
| --- | --- |
| Spine | `5af1a01af371ee9469021705ac6de8fc3cf7aa642362b1b4ea461adb2cbb3a3a` |
| FMOD | `0d5be1a919feb1d287e29b8115441c4e99d8795b8fcad031fc74699ca2a2cf62` |

## New output, startup and preservation

- **227 tracked files** passed integrity and mode checks before and after
  native execution. **23 native objects** were inspected without readelf errors.
- Pack SHA-256 is
  `25e58dc52e8f5571f54b929ce5359e9057d6d7c4e6213db920f60d7ad8a2a19a`.
  Manifest SHA-256 is
  `cf99981e2c9892f94c6e4dd2d20a790217c08c255119b7dddaf30dff38c16893`.
  Both match the earlier working output: observed reproducibility on this host,
  not a claim across toolchains.
- Headless execution of the **new output** initialized hostfxr/GodotPlugins,
  FMOD, both Sentry components and the genuine ARM64 Steam client; exit code 0.
  Steam initialization failed with missing AppID outside Steam. No AppID or
  appid file was fabricated. Owned-Steam initialization/gameplay remain untested.
- User-data/config/cache paths were isolated in the new validation directory.
  All **21 selected source files** passed hash verification afterward. The
  earlier working output passed its original manifest and mode checks.
  Original game installations and SteamOS system files were not modified.

Raw reports remain under
`/run/media/steamos/SD512/sts2-regression-validation-01`. Only sanitized metadata
is committed, not game/SDK files or raw startup logs.

The older `hardware_validation_20261008.json` describes the previous bundle and
did not validate the later SDK header-copy loop in `be471a9`. Prior SDK tests
checked header guards without executing the complete builder. This regression
test, CI coverage and exact-commit hardware run close that gap. Graphical,
owned-Steam, audio/control and save/reload acceptance remain separate.
