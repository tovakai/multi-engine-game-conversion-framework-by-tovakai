# Branch cleanup snapshot: 2026-10-12

Baseline: `a804fd696dc171474b2d34de70457f877b57bec6`.
Completed with user approval: all 31 audited remote branches were deleted using
atomic, exact-head lease checks. No changed heads were skipped. PRs #2, #9, #14,
#16, #17 and #21 are closed. The preserved heads remain in place.
Four redundant local branch copies were also removed: two matched their audited
remote heads; two were proven ancestors of the backed-up working-main baseline.
The local DDLC head `9ea3c97` is not an ancestor and remains preserved pending
separate review. Active worktrees and their branches were preserved.

The 31 pruned remote branch heads and evidence are recorded below. The private local recovery
bundle is `build/repository-cleanup-20261012/remote-heads.bundle`; it is not a public release artifact.

| Candidate | Audited head | Evidence |
| --- | --- | --- |
| `docs/brotato-tested-version-1-1-14-6` | `f51f3e6e53480e10ee6c3fe2673a04d551d97c5c` | All patches are equivalent to working-main |
| `docs/game-compatibility-table` | `b024b74d9f793f3a6bea649764dac33c98dd4f2e` | All patches are equivalent to working-main |
| `docs/link-tested-game-titles` | `5205e20bbd44069bd8c70e53d4c20b220b7eb1df` | All patches are equivalent to working-main |
| `docs/my-pig-princess-patreon-link` | `79bad8b099a9cbd704dfd90a6c095cf6005a5079` | All patches are equivalent to working-main |
| `docs/readme-table-of-contents` | `e60128e3bec4d18ce9f603edaa4262483fff519e` | All patches are equivalent to working-main |
| `docs/why-native-arm64` | `1064c86b87ee68e5408875cdbf7cbf1941a2c521` | All patches are equivalent to working-main |
| `feat/automatic-godotsteam-arm64-runtime` | `9eb37bd6433d441dce1b837025904322f7764da8` | Every changed file matches working-main or a historical version |
| `feat/construct-2-3-support` | `ce0c2c5074bd2495106def33d067e23a2dc28944` | Superseded by current unified backend/package implementation |
| `feat/custom-godot-arm64-runtime` | `08708bfdc5de06b18cd0d395f34276eaa4f04179` | Every changed file matches working-main or a historical version |
| `feat/ddlc-renpy-699-arm64-compat` | `e1c7b5e05418090d392eb1dda48bb678670166a0` | Every changed file matches working-main or a historical version |
| `feat/downloadable-godotsteam-runtime` | `cb20a956f3f55cf24641eb6dfbb2277a12a0f761` | Head is an ancestor of working-main |
| `feat/frame-package-steam-install` | `108e1a348b661a75b707a8c3fc615614c0a59a8b` | Superseded by current unified backend/package implementation |
| `feat/frame-ready-auto-runtime-integration` | `0f78450dcb3f5560a8333ad0e4563ae53ae431f7` | Head is an ancestor of working-main |
| `feat/generated-steam-shortcut-script` | `0f3803dcae6599a95ee6f68a5ea047e8e7da6975` | Superseded by current unified backend/package implementation |
| `feat/godot-custom-runtime-fingerprint` | `c87c3d19b3c83ff23bb92748d7d1982ed283cab4` | Every changed file matches working-main or a historical version |
| `feat/integrated-frame-delivery` | `5175bff3d8afaf4821622e9126920ceb5e2e9b73` | Superseded by current unified backend/package implementation |
| `feat/renpy-735-pesterquest-arm64` | `973d640d105b474d5cf6bcfa3663b4156f702b6d` | Head is an ancestor of working-main |
| `feat/steamgriddb-artwork-fallback` | `35717152de7054442d94c4d0c3ff58a453201848` | Every changed file matches working-main or a historical version |
| `feat/subfolder-detection-progress-ui` | `6dc3cbb35f069a55e77c82a7e5cbfe5f6d0f15e0` | Every changed file matches working-main or a historical version |
| `feat/tovakai-cassette-ui` | `b1217554e3fc9c6555ee22226023db34a38a24ca` | Every changed file matches working-main or a historical version |
| `fix/everlasting-summer-qt-editor-dependencies` | `ee0a272d21cf7f087d45ba1d7aa1f3a080f19273` | Every changed file matches working-main or a historical version |
| `fix/everlasting-summer-workshop-uploader-scan` | `d3a794c70741dd58d91b4039f2c9a0a72b3950f4` | Every changed file matches working-main or a historical version |
| `fix/frame-ready-preserve-renpy-bytecode` | `fb2f0c53c14be2cafa09b47f739d870b5194f284` | Every changed file matches working-main or a historical version |
| `fix/frame-zip64-streaming-renpy` | `6742c31e1cefaf35446f6df1613593c5b88b5003` | Every changed file matches working-main or a historical version |
| `fix/godot-runtime-progress` | `4a4dac5aef8f92f069e5f5a30af10f6ed83e4db3` | Every changed file matches working-main or a historical version |
| `fix/godotsteam-direct-arm64-steam-launch` | `6254b332e920b2782783473af94dbc14e29cb9b5` | Every changed file matches working-main or a historical version |
| `fix/gui-renpy-74-one-click-fallback` | `55908fa5009dcd9a7b2c4a9140d6ff085a7db08c` | Every changed file matches working-main or a historical version |
| `fix/renpy-dual-generation-version-detection` | `bcb7dd2c0683742654f0bccd948c96f5b1d3fec6` | Every changed file matches working-main or a historical version |
| `fix/renpy-preserve-bytecode` | `841447828d1808a4ddb0e4d28343b2193ff6dc07` | Every changed file matches working-main or a historical version |
| `fix/renpy-transfer-launch-and-compatibility` | `a2f3dd68036c56e14d9cbe62669824b9be5b2013` | Every changed file matches working-main or a historical version |
| `fix/windows-build-stale-output` | `c4b6b183835e6a13749ea738a64d667b1042abec` | All patches are equivalent to working-main |

## Preserve

- `audit/sts2-remove-ownership-attestation` at `f85272048dc88b2d54285cf3f2f744e0b82cff76`
- `bootstrap/digital-glitchbaby` at `bcf8310c1890ffb794c385f5397af139f51eb2f9`
- `feat/game-crash-diagnostics` at `32f239dc0a467d1f01cd3dc0a68980acc81aa9aa`
- `feat/godotsteam-arm64-recipe` at `0100b9e1d8bdb1d3de561eae6fa508055f6fc3bd`
- `feat/space-rescue-performance` at `4207c4be4720534893c2501459bf2b4a4e22fda9`
- `integration/working-main` at `a804fd696dc171474b2d34de70457f877b57bec6`
- `main` at `12bf4b889d2653dc4d48e38162a138ec156156a5`

The Space Rescue branch is checked out in an active worktree. Bootstrap mod tooling,
the old diagnostics wrapper and manual Godot packaging have unique material.
Preserve them separately; they are not necessary for 0.1.0. The remaining STS2
audit branch is excluded from this cleanup. Existing local worktrees, caches and
untracked research documents are not deletion candidates.

## Superseded open pull requests

PRs #2, #9, #14, #16, #17 and #21 were closed as superseded with user approval.
Keep #1, #11, #18 and #41 until their unique work has an explicit home.

## Promotion history

`main` has one separate README commit, `12bf4b8`, and is 97 commits behind
the audited working-main baseline. Preserve that history through a promotion PR;
do not force-push working-main over main. No promotion or release tag is created by this audit.
