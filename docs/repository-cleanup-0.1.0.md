# Repository cleanup and 0.1.0 readiness audit

Audit date: 2026-10-10. Baseline: `integration/working-main` at `7f17b10`.

This is an audit and proposed cleanup, not a branch-deletion record. No remote
branches, PRs or issues were deleted/closed. STS2 work is excluded and preserved.

## Branch classification

Inspected 41 remote branch heads: 27 redundant by ancestry,
patch equivalence or historical file evidence; 4 superseded feature
branches; four branches with unique material to preserve; two baseline branches;
and four excluded STS2 branches.

Git commit counts alone are misleading because several features were squash
merged or integrated file by file. For the first group, every changed file is
identical to working-main or a version in its history, except the six documentation
branches and stale-output fix, which also have patch-equivalent commits.

### Redundant branches suitable for pruning

| Branch | Audited head | Evidence |
| --- | --- | --- |
| `docs/brotato-tested-version-1-1-14-6` | `f51f3e6` | Patch-equivalent commits already integrated |
| `docs/game-compatibility-table` | `b024b74` | Patch-equivalent commits already integrated |
| `docs/link-tested-game-titles` | `5205e20` | Patch-equivalent commits already integrated |
| `docs/my-pig-princess-patreon-link` | `79bad8b` | Patch-equivalent commits already integrated |
| `docs/readme-table-of-contents` | `e60128e` | Patch-equivalent commits already integrated |
| `docs/why-native-arm64` | `1064c86` | Patch-equivalent commits already integrated |
| `feat/automatic-godotsteam-arm64-runtime` | `9eb37bd` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/custom-godot-arm64-runtime` | `08708bf` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/ddlc-renpy-699-arm64-compat` | `e1c7b5e` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/downloadable-godotsteam-runtime` | `cb20a95` | Tip is an ancestor of working-main |
| `feat/frame-ready-auto-runtime-integration` | `0f78450` | Tip is an ancestor of working-main |
| `feat/godot-custom-runtime-fingerprint` | `c87c3d1` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/renpy-735-pesterquest-arm64` | `973d640` | Tip is an ancestor of working-main |
| `feat/steamgriddb-artwork-fallback` | `3571715` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/subfolder-detection-progress-ui` | `6dc3cbb` | Changed file contents already occur in working-main history; later revisions supersede them |
| `feat/tovakai-cassette-ui` | `b121755` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/everlasting-summer-qt-editor-dependencies` | `ee0a272` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/everlasting-summer-workshop-uploader-scan` | `d3a794c` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/frame-ready-preserve-renpy-bytecode` | `fb2f0c5` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/frame-zip64-streaming-renpy` | `6742c31` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/godot-runtime-progress` | `4a4dac5` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/godotsteam-direct-arm64-steam-launch` | `6254b33` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/gui-renpy-74-one-click-fallback` | `55908fa` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/renpy-dual-generation-version-detection` | `bcb7dd2` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/renpy-preserve-bytecode` | `8414478` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/renpy-transfer-launch-and-compatibility` | `a2f3dd6` | Changed file contents already occur in working-main history; later revisions supersede them |
| `fix/windows-build-stale-output` | `c4b6b18` | Patch-equivalent commits already integrated |

### Superseded branches suitable for pruning after closing their old PRs

| Branch | PR | Why |
| --- | --- | --- |
| `feat/construct-2-3-support` | [#9](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/9) | Construct 2/3 detection, package.nw extraction and tests now live in RPGMFrame, with the new ConstructFrame facade. The old implementation is superseded. |
| `feat/frame-package-steam-install` | [#2](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/2) | Frame packaging, metadata, installer and Frame Control helpers are present. Its old direct-install/Devkit routes were deliberately retired. |
| `feat/integrated-frame-delivery` | [#16](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/16) | Runtime resolution, ZIP export, Steam artwork and installer are integrated and subsequently revised in working-main. The remaining egg-info ignore entry already exists as a local uncommitted edit. |
| `feat/generated-steam-shortcut-script` | [#21](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/21) | The unified install-to-steam.sh supersedes the old RenFrame-only add-to-steam.sh. Do not restore the stale branch: it also changes a launcher path to sys.argv[3]. |

### Preserve until unique work is integrated or archived

| Branch | PR | Remaining work |
| --- | --- | --- |
| `bootstrap/digital-glitchbaby` | [#1](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/1) | Contains absent mod-library/library-manager tooling, legacy renpy_arm code and imported tests. Preserve/archive these first; the current app bootstrap itself is superseded. Mod tooling belongs to the later mods milestone. |
| `feat/game-crash-diagnostics` | [#18](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/18) | tools/diagnose-game.sh is absent from working-main. Review and integrate the reusable diagnostics wrapper or explicitly defer it before deleting this branch. |
| `feat/godotsteam-arm64-recipe` | [#11](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/11) | Automatic/downloaded recipes supersede its routing, but the manual packaging script and recipe document are absent. Archive or review the utility before pruning; it includes Steam API binaries, unlike the published Brotato runtime policy. |
| `feat/space-rescue-performance` | [#41](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/pull/41) | Contains absent performance instrumentation, profiling scripts, regression tests and original-package acceptance evidence. Preserve and review; do not blindly merge its older router changes, which can omit newer migration metadata. |

### Baselines and excluded work

- Keep `main` and `integration/working-main`. The release branch should be promoted from the verified working-main baseline; do not release current main.
- At the audit snapshot, main is 87 commits behind and has one separate README commit. Its Everlasting Summer/DDLC table additions already exist in working-main; reconcile history through a release PR rather than overwriting main.
- Leave all four `*sts2*` branches out of this cleanup and release scope.
- Open PRs #14 and #17 point to branches already contained in working-main. Close them as superseded rather than merging the old implementations into main.
- The other superseded PRs are #2, #9, #16 and #21. Keep #1, #11, #18 and #41 until their unique material has a home.

## Local checkout cleanup

- Local redundant branches: `feat/downloadable-godotsteam-runtime`, `feat/frame-ready-auto-runtime-integration`, `feat/renpy-735-pesterquest-arm64`, `feat/ddlc-renpy-699-arm64-compat` and `fix/gui-renpy-74-one-click-fallback`.
- Preserve `feat/space-rescue-performance`; it is checked out in `.worktrees/space-rescue-performance`. That worktree was clean at the audit snapshot.
- A detached build worktree exists at `../multi-engine-game-conversion-framework-by-tovakai-build`. Its status was not checked because Git rejected the sandbox account ownership; verify it before removal.
- Preserve the local `.gitignore` edit, `.prototype-cache/` and `.worktrees/`. Review their contents/size before cleanup; do not recursively delete them as part of branch pruning.
- Ignored build/dist caches, local SDKs and converted games are working artifacts, not repository content. Keep the current verification ZIPs and separate cache cleanup from Git cleanup.

## Open issues

| Issue | Current status | Recommended disposition |
| --- | --- | --- |
| [#35](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues/35) | Implemented by PR #36, with recorded Everlasting Summer gameplay | Close as implemented; retain deeper compatibility limitations in the catalogue |
| [#39](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues/39) | Implemented by PR #40; Pesterquest Stages A/B and save restoration recorded | Close the implementation milestone; track broader volumes/Steam-hook testing separately if desired |
| [#37](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues/37) | DDLC migration implemented by PR #38; only Stage A verified | Keep open or split implementation from Stage B/C gameplay, saves and later-act validation; do not mark full acceptance complete |
| [#32](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues/32) | Still incomplete for general artwork provenance | Reuse steam_context.py but carry verified original source identity into artwork for RenFrame/all engines; handle conflicting identities and test it |

## 0.1.0 release work

### Required before calling it a release

1. **Freeze the advertised stable scope.** RenFrame, RPG Maker MV/MZ and compatible Godot are the strongest baseline. XP/VX/VX Ace need individual evidence or narrower claims. Keep legacy migrations, EasyRPG, Construct and the new manually provisioned SDK backends explicitly experimental; they need not block 0.1.0. LÖVE and AGS currently need clearer experimental labels in the README table.
2. **Record a candidate acceptance matrix.** For every advertised stable backend: end-to-end GUI conversion from a clean source, transfer/extract, install-to-steam.sh, native launch, real keyboard/controller interaction, short gameplay, save/load where supported, quit and relaunch. Use the final candidate build and source/runtime versions, not a mixture of old hand-fixed outputs. Retest original problem titles where support is claimed. Startup-only Godot candidate evidence does not establish gameplay support.
3. **Implement the agreed version/provenance policy after candidate retesting.** pyproject.toml already says 0.1.0, but there is no common application version API, umbrella CLI --version, GUI About version or converter version/commit in game manifests. Application/game ZIP names are unversioned. Centralize the version, keep game version separate, implement the roadmap naming policy and test every archive consumer.
4. **Build clean distributable artifacts.** Windows currently has a manual build script and local frozen-app verification. Add a Windows CI build/smoke gate, run the existing Linux ARM64 build on the candidate commit, validate packaged resources/architecture and archive extraction on clean installations. Ship versioned Windows and Linux ARM64 archives with commit, checksums, setup instructions and notices.
5. **Make release publication deliberate and repeatable.** There is no application release workflow and no application GitHub release; the only existing release is the Godot runtime prerelease. Add tag/release packaging and asset upload (or a documented manual equivalent). The Linux build is triggered by PRs, workflow_dispatch or v* tags, not normal working-main pushes. Avoid letting runtime-only tags accidentally imply an application release.
6. **Promote the verified baseline.** Reconcile working-main into main through a reviewed release PR after acceptance. Consider requiring passing tests/builds on main; neither baseline branch is protected and the repository has no rulesets. Tag v0.1.0 only after artifacts and claims match the tested commit.

### Cleanup and useful fixes before or alongside release

- Close superseded PRs and completed implementation issues, then prune the identified redundant branches. Preserve old heads in an archive/bundle if desired before deleting refs.
- Finish #32 artwork provenance for the original source. The new helper is used for native-engine/Steam launch metadata, but official artwork still discovers identity only from built-output sidecars; ordinary RenFrame Steam installs can miss artwork.
- Review PR #18 diagnostics and PR #41 performance tools; include a small reusable diagnostics path if ready, otherwise explicitly defer them without delaying the foundation release. Do not blanket-merge old router files.
- Review/archive bootstrap mod-library functionality for the later mods milestone and the old manual Godot packager; do not bring obsolete app namespaces back into the public application.
- Refresh README architecture, bytecode inspection description (it still describes host-version-only inspection), backend status labels and the Linux package README. Link new native backend setup/status consistently.
- Consolidate compatibility evidence into a maintained table with exact game/runtime version, converter commit, input, gameplay, save/relaunch results and limitations. Keep original DDLC later-act testing and new Godot candidate gameplay separate from stable-backend release gates.
- Consolidate CI/package metadata and release notes; add a 0.1.0 milestone/checklist. No GitHub milestones were configured at the audit snapshot.

### Explicitly deferred

- STS2 research, integration, remote builds and device-side finalization.
- The full 35-title matrix, broad GameMaker runner compatibility and WOLF RPG support.
- Full DDLC story certification, GodotSteam co-op/workshop/online certification, mod-library integration and automatic device transfer unless independently ready.

## Suggested sequence

Before deleting a remote ref, verify that its head still matches the audited
snapshot; new commits invalidate the deletion recommendation. Preserve unique
branch work → close superseded PRs/issues → prune redundant branches
→ freeze stable claims and run the candidate matrix → unify versioning/packaging
→ clean builds and artifact checks → reconcile to main → publish v0.1.0.
