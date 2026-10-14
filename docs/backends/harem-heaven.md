# Harem Heaven 0.3.5.1: native ARM64 research result

User SteamVR testing reported "All works" for the menu/gameplay, Spine
animations, audio and input. The running engine was verified as an AArch64
Linux ELF. Headless startup and shutdown completed with exit status zero and
no script/resource errors. Saving, relaunch and normal visible-session exit
were not separately verified.

The Windows export uses Godot **4.6.2** and Spine skeleton data **4.3.08**.
The official Godot ARM64 release export template was verified against the
upstream archive checksum. The supplied Spine descriptor includes ARM64 paths,
but the official 4.6.2 extension archive contained only an x86_64 Linux binary.
A native release extension was therefore built from official Spine **4.3**
sources against Godot C++ API **4.6**, with four low-priority build jobs.

- Spine source commit: `fc2ae27725c886d886fd88d9621c3e665c234615`.
- Godot C++ source commit: `b8530af7546a3fcae80cef2477526569fd42ffc2`.
- Engine SHA-256: `214731ad7eb5e33fdb706df42231ecae301fb30b0e3eaaad09eec9c01bb17908`.
- Extension SHA-256: `564c498b5e70b151c59b68195b2caea08921d9f50b7bcf41a4f9ddfdc2551597`.
- Unchanged source pack SHA-256: `c8da3662ae8d33962c0b5d6e49194b46642eefa19247176a54ed8f9b2c71d042`.

Godot 4.6.2's hardened release template rejects `--main-pack`. The existing
shared adjacent-pack launcher contract loads `godot.pck` beside `godot.arm64`.
The native extension lives in `bin/linux/` beside that pack, and `override.cfg`
selects the isolated `megcfbt/research/harem-heaven-0351-20261014` save namespace.
The original game pack is byte-identical; no game or engine-source patches
were needed. The three shipped companion-tool files were preserved.

The live test entry is **Harem Heaven [ARM64 test]**. No trustworthy Steam AppID
was found; no identity or ownership was inferred from its directory/title.
The shared installer added it as a non-Steam game without restarting Steam.
Automatic original-entry linking, asset deduplication, Steamworks features and
automatic converter provisioning are not advertised for this research result.

Godot, Godot C++ and Spine license notices accompany the private test package.
Spine has its own [runtime license](https://github.com/EsotericSoftware/spine-runtimes/blob/4.3/LICENSE),
not an MIT license. Public redistribution/provisioning requires a separate
license review; this research test creates no public runtime or application
release. See the [official Spine-Godot documentation](https://en.esotericsoftware.com/spine-godot).
