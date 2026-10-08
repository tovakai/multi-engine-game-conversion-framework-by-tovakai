# STS2 automatic-converter release blockers

The source pipeline is routed through the framework CLI and desktop, but the
ordinary-user objective is not yet complete. Track these four independent gates.

## 1. FMOD licensing and acquisition

The converter needs the original FMOD Studio API 2.03.15 Linux SDK. Its proprietary
ARM64 runtimes cannot be generated from the Windows game DLLs by this pipeline.
The current alternative imports a user-authorized vendor SDK archive with full
archive, runtime and C/C++ header checksums; it does not distribute SDK binaries.
Official downloads require authentication. Applicable FMOD and Spine integration
permissions also remain a release gate; game ownership is not asserted to grant
those permissions.

Next step: establish a vendor-authorized acquisition flow and applicable rights,
then integrate that flow into dependency setup. Until then the application must
expose the SDK prerequisite, rather than imply installation-only conversion.
See [official FMOD downloads](https://www.fmod.com/download),
[FMOD licensing](https://www.fmod.com/licensing), and the
[Spine Runtimes license](https://esotericsoftware.com/licenses/Spine-Runtimes-License-Agreement.pdf).

## 2. Clean retail source verification

The supported profile is only v0.98.2 / f4eeecc6. The matching testgames fixture
was authorized for comparison, and its selected inputs match the preserved
profile, but publisher-pristine provenance is unverified. Replacement Windows
Steam DLLs and settings are excluded from conversion. The observed retail Steam
installation is v0.107.1 / 59260271 and remains rejected.

Next step: verify a legitimate untouched retail/depot copy of the supported
build, or derive and independently validate a separate recipe for a retail build.
Neither relaxed hashes nor guessed patch offsets satisfy this gate.

## 3. Owned-Steam gameplay acceptance

Headless SSH startup can establish native subsystem initialization, not owned
Steam initialization or gameplay. No AppID environment variable or appid file is
manufactured to make that test pass. The Frame now has an STS2 appmanifest;
acceptance still needs the generated output launched through that owned entry.

Next step: validate real Steam initialization, main menu, rendering, audio,
controls, save/reload and normal shutdown with the newly generated directory.
Achievements and cloud synchronization require separate observed evidence.
Preserve prior launch options and all existing installations for rollback.

## 4. Windows/x86-64 build hosts

The current source compilation path requires a Linux AArch64 host and its native
toolchain. The Windows/x86-64 application detects STS2 and explains prerequisites,
but cannot yet perform the complete source build from that host.

Next step: add a framework-managed remote AArch64 builder (including SSH host
verification, isolated workspaces, progress, pinned tool setup, dependency
acquisition, output verification/transfer and failure recovery), or a validated
cross-compilation toolchain. Remote execution must use the same backend and
source guards; it must not fetch extension binaries from a prior conversion.

These gates are separate from the SDK-loop regression and from static output
integrity. Passing unit tests or producing a valid directory does not close them.
