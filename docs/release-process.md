# Application release process

Application releases and downloadable engine runtimes have separate tags and
artifacts. Runtime-only tags must not imply that a converter release was tested.

## Build and review a candidate

Use Python 3.12 to build. On Windows run `powershell -ExecutionPolicy Bypass -File
build/build_windows.ps1`; on native Linux ARM64 run
`bash build/build_linux_aarch64.sh`. The builders install the declared GUI/build
dependencies and generate versioned archives with executable architecture checks.

For a native Linux x86_64 converter, run `bash build/build_linux_x64.sh`.
Both wrappers use `build/build_linux.sh`; converter host architecture does not
change the Linux ARM64 game runtime target. Linux builders collect certifi CA
data and license metadata. The Linux CI matrix checks both application targets;
its optional `tls_network_smoke` workflow-dispatch input requests official NW.js
checksum metadata through the frozen downloader. The default build is offline
after dependency installation and does not download an NW.js archive.
The PR label `tls-network-smoke` also opts that PR into the checksum-only live
check on both native runners; no archive is downloaded by the smoke step.

The Windows and native ARM64 CI workflows also build the application, start the
actual frozen GUI in its verification mode and upload the archives, checksums
and startup receipts. The ordinary test workflow runs on Windows and Linux.
GitHub's ARM64 runner support is documented in its
[hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Check each archive's `BUILD.json`, `BUILD.txt`, `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `RELEASE-NOTES.md` and adjacent SHA256SUMS file.
`tracked_changes` must be false for a published release. CI/startup success is
not a substitute for the representative game conversion/install acceptance matrix.

The current version is defined in `megcfbt.__version__`; bundled RenFrame and
RPGMFrame share it. `pyproject.toml` must agree, and archive generation rejects
a mismatch. The CLI reports it with `--version`.

## Promote and publish deliberately

1. Review the candidate scope, known limits, hardware evidence and passing checks.
2. Reconcile `main` history through the working-main promotion PR; do not replace
   main with a force push or merge obsolete feature implementations individually.
3. Merge the reviewed PR. Build and verify both archives from the resulting exact
   main commit. Keep the full source commit in each artifact's provenance.
4. After acceptance, create `v0.1.0` on that commit. The tag triggers both build
   workflows; inspect their results before uploading application release assets.
5. Publish the application release with reviewed notes, the Windows ZIP, native
   Linux ARM64 tarball, and checksums. Use a notes file with `gh release create`;
   verify release asset names and hashes after upload.

Release publication is a manual final step. The workflows do not automatically
publish a release merely because a branch or tag was pushed. Test/diagnostic
receipts belong in CI artifacts; private game files, converted games, vendor SDKs,
runtime caches and branch-recovery bundles must never become release assets.

The source archive attached to GitHub's tag provides the converter source;
downloadable runtime bundles retain their own source/license requirements.
