# Train45: experimental native ARM64 conversion

The shared GUI and CLI recognize audited Steam build **25227748**, Godot
**4.5.0**, and GodotSteam GDExtension **4.19.1**. Conversion extracts the
embedded pack, verifies its complete SHA-256 plus the source extension hashes,
and installs the checksum-pinned ARM64 **release** runtime and extension.
A changed game build requires a newly audited profile. No title lookup or
unverified AppID sidecar establishes Steam identity or ownership.

Select/drop the installed Train45 directory into the GUI and click **CONVERT**.
No FMOD SDK or compiler is required. The development Windows build bundles the
verified open-source runtime archive. Public runtime provisioning remains a
release-preparation gate; source checkouts without that archive can use an
extracted, verified bundle with `--backend-runtime`.

```powershell
python -m megcfbt build "C:\Program Files (x86)\Steam\steamapps\common\Train45"
```

Transfer the generated versioned ZIP to Frame, extract it, and run
`./install-to-steam.sh`. Choose **Add as non-Steam game**. The shared installer
preserves duplicate detection and live artwork registration. Original-entry
linking and game-asset deduplication are not approved for the shared Godot launch
contract. This limitation is backend-wide, not evidence that Train45 failed.

The original game files remain untouched. Converted saves use
`~/.local/share/megcfbt/train45`. Research saves remain in
`~/.local/share/megcfbt/research/train45-20261014`; preserve them when migrating.
Existing source `override.cfg` is retained as `source-override.cfg`.

The package uses Frame's installed native Steam API at
`/opt/steamvr/bin/linuxarm64/libsteam_api.so`; its launcher creates a dependency
symlink inside the converted package and rejects unexpected files or symlinked
parent directories. This is runtime dependency resolution, not game-asset
deduplication. The runtime bundle contains no game data or Valve binary. Genuine
Steam initialization is retained; selecting the audited AppID does not grant
ownership or fabricate successful Steamworks calls.

## Validation and limits

A separate research package passed user gameplay testing on Steam Frame.
Native Godot and the Steam extension were verified as AArch64 ELF binaries;
release-mode headless startup and genuine Steam initialization passed. The
editor runtime was deliberately replaced because it enabled the game's debug
Steam mode. No game scripts/assets required patches.

Production inspection/backend/router/ZIP regressions verify both metadata
copies, identity conflicts, modified assets/runtimes, cached offline provisioning,
source preservation and repeated conversion. The actual frozen-GUI package
needs separate Frame acceptance. Full-game coverage, achievements, playtime and
Steam Cloud remain unverified. Headless exit reports ObjectDB/resource cleanup
warnings. This profile does not make v0.1.1.0 release-ready.
