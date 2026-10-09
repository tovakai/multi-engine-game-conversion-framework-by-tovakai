# Windows GUI → Frame STS2 conversion architecture

Work branch: `feat/sts2-windows-frame-workflow`, starting at `6761a4f`.
STS2 remains experimental until the packaged GUI, supported untouched retail
source and owned-Steam gameplay have all been exercised.

## Audit

The existing router already identifies STS2 before generic Godot and delegates
to the standard-library source pipeline. Its GUI worker is asynchronous, but
its conversion-availability check requires a local AArch64 toolchain. A frozen
Windows build also tries to execute a separate Python interpreter for inspection.
The builder always clones/compiles; public runtimes alone have a verified cache.
The proven Steam helper preserves the owned wrapper/reaper chain, replaces FEX
with the installed native Valve host runtime and never assigns Steam identities.
Retail v0.107.1 currently has no guarded conversion recipe.

## Design

1. Keep the converter as the sole transformation implementation. Load its
   inspection helpers in-process on Windows, including PyInstaller builds.
2. Add an STS2 backend remote service. It owns settings, secure transport,
   preflight, source/SDK transfer, dependency setup, build/deployment and recovery.
   Generic GUI/router code calls this service rather than implementing SSH steps.
3. Use the installed OpenSSH client with existing keys/config/agent. Enforce
   batch authentication and verified known-host identities. First-use key
   fingerprints require explicit GUI trust; unknown/changed keys never silently
   pass. Store host/user/path/key-file references, never passwords/private keys.
4. Probe the real Frame before conversion: AArch64, Python, Git, compiler,
   readelf, available writable storage, pinned Valve API and host runtime.
   Provision pinned SCons only into a private reusable environment; no root or
   system package installation. Missing compiler prerequisites are a clear block.
5. Validate every selected source file locally before expensive transfer.
   Build a software-only backend bundle and a selected-input archive; forbid
   symlinks/unsafe names. Upload into UUID workspaces under the configured
   writable directory. Verify content hashes remotely before safe extraction.
6. Run the existing `pipeline.py` remotely. Stream stage progress and private
   diagnostics. Reuse public archives after hash verification. Cache compiled
   extensions only with exact source/SDK/toolchain recipe provenance and verified
   file/ELF/export hashes; never search experimental game outputs for dependencies.
7. Publish a new verified native output in the selected remote destination.
   Optionally download a verified transfer archive into the selected local output
   directory. Never overwrite prior outputs. Record a resumable job identifier;
   retain failed workspaces for diagnosis, restrict cleanup to app-created jobs.
8. Supply a generated persistent short Steam entry point and copyable launch
   command. Preserve real Steam context and make test-data isolation explicit.
   Steam options are not modified automatically.

## GUI

Drag/drop uses existing inspection and routing. An STS2 setup dialog guides host,
identity-file selection, trust/probe, authorized SDK selection and destination.
The backend validates/persists this configuration. Conversion runs in the
existing worker, with transfer/build/verify/deploy progress and actionable errors.
Success presents the remote path and a copyable Steam command. Other backends
continue through their current paths.

## Retail and validation gates

Inspect the legitimate Windows v0.107.1 assemblies, graph and pack without
executing them. Derive a separate recipe from semantic/IL evidence, source pins
and native ABI compatibility, not old offsets. Keep unsupported inputs refused
if this cannot be proven. GUI/transport work proceeds independently of that gate.

Validate unit/failure-path tests, actual Windows development GUI, packaged Windows
GUI and real automated remote conversion. Use original supported retail bytes
when available; any old-version comparison fixture is labeled separately.
Game/SDK/native outputs, private settings and logs remain outside Git publication.

## Owned Steam integration revision

The success screen offers a consent-gated **Connect Steam** action. This uses
Steam's local SharedJSContext `SteamClient.Apps.SetAppLaunchOptions` API for the
real owned STS2 entry. It neither creates a shortcut nor edits live VDF files.
The selected output is verified before any change. A private, durable backup of
the previous per-game launch setting is saved next to the job. Restore refuses
to overwrite intervening user edits. Connection and Restore are asynchronous;
the last output association is remembered across application restarts.

The local Steam UI endpoint must already be available. The application does not
change SteamOS configuration to enable it. Unsupported clients fail with a
clear diagnostic and retain their existing launch configuration.
