# Barely Working: native ARM64 research result

User Steam Frame testing confirmed the native package works well. Startup
verified Godot **3.5.3**, GLES2 and Zink/Turnip on the Adreno 750. Game content
remained unchanged; source pack SHA-256:
`eca74556f47d349ad503e0970968a1b88ed84e3101cd7ad1e79013c05cf7f5a8`.

There is no official Linux ARM64 binary in the 3.5.3 release. A release export
runtime was compiled from Godot tag `3.5.3-stable`, commit
`6c814135b69d4e703956bacc2073b4b179ff5a00`, using Clang 19.1.7 on Frame.
No engine or game-source patches were needed. Build options:

```text
scons -j4 platform=x11 tools=no target=release bits=64 use_llvm=yes
use_lld=yes use_lto=no use_static_cpp=no
CXXFLAGS="-include cstdint -include cstddef"
```

The stripped AArch64 binary is 37,010,336 bytes, SHA-256
`cd932bfe3a7e03249fd0b7cfee927bc37a63a92488f820eae9ebfec7cb946882`.
It uses Frame's installed shared C++/atomic libraries. The runtime is preserved
with its license, copyright and build provenance for manual converter selection.
Automatic provisioning and frozen-GUI package acceptance remain unfinished;
this note does not advertise automatic conversion support.

The sole test entry is **Barely Working [ARM64 test]**. Its files and research
saves remain intact; saves use `megcfbt/research/barely-working-20261014`.
No trustworthy Steam AppID was found. Original-entry linking and asset
deduplication remain unsupported. The game's own icon was installed through
Steam's live artwork API without a restart. Gameplay was user-confirmed;
save/relaunch, playtime and achievements were not separately verified.
