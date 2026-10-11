# RenFrame Live2D runtime provisioning

Some Ren'Py games depend on Live2D Cubism Core in addition to Ren'Py. Official
Ren'Py SDK archives do not include this proprietary library. A runtime transplant
or full-engine upgrade must supply a matching native library separately.

RenFrame detects loose Live2D model files and shipped Windows Core libraries.
When those markers are present, the GUI requires a Linux ARM64 Core and opens a
download/import dialog if one is missing. Obtain the current stable **Cubism SDK
for Native** ZIP from [Live2D](https://www.live2d.com/en/sdk/download/native/), reading
and accepting the vendor agreements yourself. Keep the ZIP in Downloads for
automatic discovery or select it in the dialog. No vendor download or agreement
acceptance happens automatically. Discovery cannot identify every model hidden in
custom or encrypted archives; missing loose markers do not prove a game has no
Live2D dependency.

The importer selects only the Linux ARM64 Core and its Core license notice.
Android ARM64, Linux x64 and Windows libraries are incompatible and rejected.
The accepted Core is hashed, cached and rechecked before reuse, then copied into
`lib/py3-linux-aarch64` (or `lib/py2-linux-aarch64` for Python 2) in each converted output. Its notice and a runtime manifest
accompany that copy. The original installation and downloaded SDK remain intact.
The converter executable/ZIP contains no vendor Core or SDK payload.

The SDK's experimentally named Linux ARM64 directory is supported with either
`arm64` or `ARM64` spelling. This is a native Linux library, not an Android shim.
Core ABI and model compatibility still require hardware testing for the particular
game and Ren'Py version.

Initial validation: Broken Sky V0.6.2Alpha, nightly Ren'Py 8.4.1.25071908 upgraded
explicitly to matched 8.5.3 engine/runtime. User-supplied SDK 5-r.5 supplied Core
6.0.1. It resolved the missing-Core native crash on Steam Frame and reached a
rendered important-notice screen. Gameplay, animation sequences and saves remain
unverified. See [the hardware report](hardware-feedback-2026-10-11.md).
