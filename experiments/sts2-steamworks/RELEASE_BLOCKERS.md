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

A separate v0.107.1 / 59260271 recipe now exists. It was derived from the supplied
legitimate Windows Steam installation, with exact selected-input hashes,
version-specific guarded managed IL edits, dependency-graph and packed-manifest
checks. Both development and packaged Windows GUIs have performed real remote
conversions from that installation. Publisher/depot provenance beyond the
supplied installation is not independently attested by these local hashes.
The old v0.98.2 testgames fixture still has unresolved pristine-source provenance.
Unsupported versions remain refused; no future offsets or hashes are guessed.

The first retail menu test exposed a Spine manifest-relative path mismatch.
The corrected retail recipe and staged native-binding validation prevent that
placement error. Fresh Frame smoke tests of corrected development and packaged
outputs pass. Full retail gameplay acceptance remains a separate gate.

## 3. Owned-Steam gameplay acceptance

Headless SSH startup can establish native subsystem initialization, not owned
Steam initialization or gameplay. No AppID environment variable or appid file is
manufactured to make that test pass. An isolated development output has now
reached the graphical main menu through the owned Steam entry: genuine Steam
initialization, native Vulkan, .NET and FMOD initialization were observed, and
the earlier user report confirmed booting. A fresh retail conversion produced
through the packaged Windows GUI has now reached the owned-Steam menu, with
audio and controller navigation confirmed by the user and Spine/native subsystem
loading verified in fresh logs/process mappings. This validates menu startup,
not extended gameplay, save/reload or cloud synchronization.

Next step: validate audio, controls, extended gameplay, save/reload and normal
shutdown with the generated directory when normal user-data writes are authorized.
Achievements and cloud synchronization require separate observed evidence.
Preserve prior launch options and all existing installations for rollback.

## 4. Windows/x86-64 build hosts

The Windows desktop application now manages remote builds on the Frame through
verified OpenSSH, using the same source pipeline. Actual development and packaged
GUI tests selected retail source, transferred verified inputs, compiled pinned
extensions (then reused a verified application cache), deployed and verified
native output. SCons is provisioned privately from a pinned wheel. No root,
system partition change, cross toolchain or manually assembled game binary is
required. Host/key/destination/authorized SDK setup is persistent and reusable.

The packaged GUI can configure the real owned Steam entry after explicit consent
and back up its previous launch setting. Restore preserves intervening user
edits. Users do not need to edit Launch Options. This currently depends on the
Frame's already available local Steam UI API; unsupported clients fail safely.
Read [current validation](../../docs/sts2-gui-validation.md) for exact evidence
and the distinction between packaged conversion, native startup and gameplay.

Remaining usability/reliability gates include extended interrupted-job/recovery
coverage, optional archive-download recovery, broader clean-machine setup and
normal gameplay acceptance. Passing this host milestone does not resolve vendor
rights or establish official compatibility.

These gates are separate from the SDK-loop regression and from static output
integrity. Passing unit tests or producing a valid directory does not close them.
