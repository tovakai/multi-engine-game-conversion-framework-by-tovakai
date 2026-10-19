# Application release process

Application releases and downloadable engine runtimes have separate tags and
artifacts. Runtime-only tags must not imply that a converter release was tested.

## Build and review a candidate

For v0.1.1.0 Steam Library Integration, use the
[mandatory Frame acceptance checklist](steam-library-integration.md#required-steam-frame-acceptance).
Candidate CI archives remain development builds until those checks are reviewed.
Keep v0.1.0.3 immutable; do not create the public v0.1.1.0 tag or publish final
artifacts while required installation, launch, restoration or hardware checks
remain unverified. Playtime and achievements require separate evidence.

Revised v0.1.1.0 scope (2026-10-15): non-Steam installation is the recommended
main workflow. Original-entry linking and deduplication remain optional
**[experimental]** features. Their unfinished hardware qualification checks do
not block publication; they remain required before removing experimental status.
Safety guards, truthful capability reporting and non-Steam regression checks
continue to be release requirements. See the acceptance ledger for the current
publication gates rather than treating the historical experimental matrix as
mandatory stable-feature acceptance.

Use Python 3.12 to build. On Windows run `powershell -ExecutionPolicy Bypass -File
build/build_windows.ps1`; on native Linux ARM64 run
`bash build/build_linux_aarch64.sh`. For native Linux x86_64 run
`bash build/build_linux_x64.sh`; both wrappers use the shared native builder.
A mismatched host architecture fails before dependency installation. The builders install the declared GUI/build
dependencies and generate versioned archives with executable architecture checks.

The Windows and native ARM64 CI workflows also build the application, start the
actual frozen GUI in its verification mode and upload the archives, checksums
and startup receipts. The ordinary test workflow runs on Windows and Linux.
GitHub's ARM64 runner support is documented in its
[hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Check each archive's `BUILD.json`, `BUILD.txt`, `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `RELEASE-NOTES.md` and adjacent SHA256SUMS file.
`tracked_changes` must be false for a published release. CI/startup success is
not a substitute for the representative game conversion/install acceptance matrix.

The sole maintained release number is `RELEASE_VERSION` in `megcfbt/version.py`.
Setuptools, bundled backends, GUI, CLI and archive names derive their build version
from it. See [versioning](versioning.md) for development identities and game provenance.
The builders resolve `build/_build_info.json` **before** freezing. Archive generation
rejects source changes since that snapshot; CI checks the actual frozen GUI/CLI
receipt against archive metadata, names and checksums. Full history is fetched.

## Promote and publish deliberately

1. Review the candidate scope, known limits, hardware evidence and passing checks.
2. Reconcile `main` history through the working-main promotion PR; do not replace
   main with a force push or merge obsolete feature implementations individually.
3. In a reviewed release-preparation PR, set only `RELEASE_VERSION` to the intended
   public number (for example `0.1.1.0`) and add `docs/releases/<version>.md` notes.
   Merge after acceptance and verify development candidate builds from the exact
   main commit. No version bump is needed for ordinary commits.
4. After approval, create `v<version>` on that accepted commit. Rebuild both official
   archives from the tagged checkout. Tag-triggered workflows reject invalid or
   mismatched versions, shallow history and tracked source changes before freezing.
   A local official build must also use the exact matching tag and clean tree.
   Inspect both workflows before uploading assets. Do not move or recreate old tags.
5. Publish the application release with reviewed notes, the Windows ZIP, native
   Linux ARM64 and Linux x64 tarballs, and checksums. Use a notes file with `gh release create`;
   verify release asset names and hashes after upload.

Release publication is an explicit final step. Ordinary branches and tags do not
publish releases. For 0.1.1.2, the maintainer may opt the accepted release-preparation
PR into publication with label `publish-0.1.1.2` before merging it into main.
`.github/workflows/publish-release.yml` verifies that main still equals that
accepted merge, creates the immutable matching tag, rebuilds all three official
platform archives from it, runs frozen checks, and validates archive metadata,
architecture and SHA256. It uploads a draft, downloads and verifies its assets,
then publishes it. A manual workflow dispatch provides the same deliberate opt-in.
The workflow refuses to move existing tags or overwrite an already published
release. Its assets are only the three converter archives and SHA256SUMS.txt. Test/diagnostic
receipts belong in CI artifacts; private game files, converted games, vendor SDKs,
runtime caches and branch-recovery bundles must never become release assets.

The source archive attached to GitHub's tag provides the converter source;
downloadable runtime bundles retain their own source/license requirements.
