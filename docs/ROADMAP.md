# Roadmap to v1.0

**Project:** Multi-Engine Game Conversion Framework by Tovakai  
**Primary reference device:** Steam Frame  
**Target format:** Native Linux AArch64 game packages

> This roadmap sets release goals, not promises or dates. A feature only counts as supported after repeatable conversion and real-device testing. Existing working functionality may be improved before its planned milestone.

## Mission

Let users provide their own legitimately acquired PC games, detect the engine and runtime requirements, and produce native Linux AArch64 packages without rewriting or distributing the original game. Keep one coherent GUI and CLI, favor reusable engine-level fixes, and report unsupported cases accurately.

## Release overview

| Version | Theme | Primary outcome |
| --- | --- | --- |
| **0.1.0** | Foundation | Reliable existing backends and consistent GUI-to-device workflow |
| **0.2.0** | GameMakerFrame + coverage baseline | GameMaker support and a 35-title test matrix |
| **0.3.0** | WebFrame | Construct and compatible packaged HTML5 game support |
| **0.4.0** | Compatibility Engine | Reusable, versioned repair recipes and local compatibility data |
| **0.5.0** | Device Integration | Convert, transfer and install on Steam Frame without terminal work |
| **0.6.0** | Mods & Saves | Safe mod profiles and verified save migration |
| **0.7.0** | Compatibility Marathon | Broader hardware coverage, regressions and community test reports |
| **0.8.0** | Experimental Expansion | Investigate harder engine families behind isolated feature gates |
| **0.9.0** | Public Beta | Stable builds, distribution, documentation and external testing |
| **1.0.0** | Stable Release | Dependable, documented ARM64 game conversion platform |

---

## v0.1.0 — Foundation

**Goal:** Make the existing engine paths dependable before expanding.

- Stabilize RenFrame, RPGMFrame and Godot conversion/routing in the unified application.
- Preserve supported Ren'Py 7/8 workflows and explicit, opt-in legacy migrations.
- Maintain RPG Maker XP/VX/VX Ace (mkxp-z), MV/MZ (NW.js), and compatible Godot runtime replacement.
- Standardize inspection, GUI/CLI behavior, build output, errors and diagnostics.
- Keep official runtime downloads validated and cached; preserve original game files.
- Stabilize existing Linux AArch64 packaging, Steam Frame installation instructions, and native launching.
- Add representative automated regression tests for every advertised stable backend.
- Keep experimental or manually provisioned backends clearly labeled; they do not block 0.1.0.

**Release gate:** Each advertised stable backend has an end-to-end GUI conversion, regression coverage, and at least one real-hardware gameplay check. A successful build alone does not count as playable. **Portable device-side finishing for STS2, automatic on-device compilation and zero-SSH installation are explicitly out of scope for 0.1.0.**

## v0.2.0 — GameMakerFrame + coverage baseline

**Goal:** Add GameMaker Studio support while proving the existing backends across a meaningful set of games.

### GameMakerFrame

- Detect GameMaker generation and distinguish VM bytecode from native-code/YYC constraints where possible.
- Evaluate and integrate Butterscotch as a candidate open-source ARM64 runner.
- Evaluate GMLoader-Next as an alternative where its runtime dependencies and distribution terms permit.
- Select compatible runtimes, prepare game data, and package native AArch64 launchers.
- Provide clear diagnostics for incompatible versions, extensions and YYC-only builds.
- Use Undertale and Pizza Tower as initial compatibility candidates, subject to successful on-device verification.

### Coverage target

Test and document **35 distinct game titles**, using user-provided game installations:

- **20 Ren'Py titles**
- **10 RPG Maker titles**, spread across relevant engine generations
- **5 Godot titles**

For each title, record the game version, detected engine/runtime, conversion outcome, Steam Frame launch or gameplay result, required fixes and outstanding issues. Titles that fail are still useful test coverage when the failure is reproduced and documented; the target is **35 tested titles, not 35 guaranteed successes**.

**Release gate:** At least two GameMaker games convert through the GUI and launch on Steam Frame without manual patching; the 35-title Ren'Py/RPG Maker/Godot test matrix is documented with real hardware outcomes.

## v0.3.0 — WebFrame

**Goal:** Support compatible packaged browser-game runtimes.

- Add a separate WebFrame backend, starting with Construct 2 and Construct 3 exports.
- Detect HTML5/NW.js packaging and distinguish recognized engines from arbitrary websites.
- Reuse relevant NW.js compatibility work already present in RPG Maker MV/MZ support.
- Replace incompatible host runtimes with suitable Linux AArch64 alternatives.
- Handle local file access, audio, input, fullscreen behavior and save storage.
- Report unsupported wrappers, obfuscation or native extensions instead of guessing.

**Release gate:** At least three representative packaged games, including Construct 2 and Construct 3 cases, convert and reach playable gameplay on Steam Frame.

## v0.4.0 — Compatibility Engine

**Goal:** Make recurring fixes reproducible instead of repeatedly patching individual games.

- Introduce versioned compatibility profiles identified by engine signatures, runtime versions and relevant file hashes.
- Separate generic engine/platform repairs from narrowly scoped title-specific overrides.
- Support safe, declarative repair recipes with dry-run inspection and rollback.
- Record runtime selections, applied fixes, dependencies and test provenance in package manifests.
- Maintain a local compatibility database and optionally fetch reviewed profile updates.
- Never apply a recipe when version or identity checks do not match.

**Release gate:** Previously manual conversions work through reviewed profiles without editing package contents by hand or adding per-game branches to the application's core routing logic.

## v0.5.0 — Device Integration & Device-Side Finalization

**Goal:** Support a portable, offline-first "Convert on PC → copy ZIP → finish on ARM64 device → play" experience, without requiring remote access to the device during conversion.

- Introduce a reusable **Device-Side Finalization** contract for backends whose final ARM64 dependencies or builds must be completed on the target device.
- **STS2 reference workflow:** On Windows, identify and validate a supported game version, perform platform-independent transformations, and produce a self-contained **software-only installer + user-supplied game-data ZIP**, without requiring a Frame IP address, SSH, Steam settings changes or FMOD SDK at this PC preparation stage.
- After the user manually copies and extracts the ZIP on Steam Frame, provide an obvious graphical/desktop installer (and CLI fallback) that performs remaining native ARM64 build work, validates hashes/architectures and reports actionable failures.
- Find and reuse previously supplied/cached FMOD 2.03.15 Linux SDK inputs; if missing, link to the [official FMOD download page](https://www.fmod.com/download) and guide the user through providing the exact compatible archive. Do not redistribute proprietary SDK files or assume unattended downloads behind sign-in.
- Build/install required native libraries on-device only when toolchain and permissions allow; provide transparent prerequisite diagnostics and resumable work rather than modifying system partitions.
- Offer explicit, reversible **Connect Steam / Restore Steam** where a game technically depends on an existing Steam launch context; never demand a purchase declaration, spoof Steam identity or alter Steam settings without consent.
- Preserve the current STS2 Windows-to-Frame remote-build workflow as an optional advanced/developer path during migration.
- Optionally discover/configure devices over SSH and transfer packages directly; direct device access is an enhancement, not a requirement for ZIP creation.
- Support repair, updates, uninstall, source protection, package manifests, output verification, and portable Linux AArch64 output beyond Steam Frame.

**Release gate:** A user can select supported STS2 source files on Windows and create a transferable ZIP **without a Frame connection**. On a compatible Frame with necessary build prerequisites, the extracted installer finishes and verifies a native build, then offers reversible Steam integration. At least one clean-device install and one cached reinstall pass gameplay/save-relaunch testing. Missing vendor SDK or unsupported toolchain produces a specific, recoverable diagnostic. Existing simple-engine ZIP conversions remain unchanged.

## v0.6.0 — Mods & Saves

**Goal:** Preserve more of the user's existing game experience.

- Incorporate the existing Ren'Py mod-library work into the unified application.
- Add compatible RPG Maker plugin/mod workflows where feasible.
- Provide per-game mod profiles, backups, conflict detection and reversible changes.
- Identify native x86 dependencies in mods and explain when they cannot run on ARM64.
- Detect and migrate compatible save paths/formats between source and ARM64 installations.
- Keep modded builds separate from clean base-game conversions.

**Release gate:** At least two engine families demonstrate safe mod/profile handling, and representative save transfers are verified after relaunch.

## v0.7.0 — Compatibility Marathon

**Goal:** Improve depth, resilience and confidence across supported backends.

- Expand testing across engine generations, runtime versions, game genres and troublesome edge cases.
- Prioritize shared engine-level fixes over one-off workarounds.
- Track conversion, launch, brief gameplay and deeper gameplay as distinct statuses.
- Turn real hardware failures into reproducible tests and reviewed compatibility profiles.
- Establish a contributor-friendly format for reports with version, device, runtime, logs and reproduction steps.
- Re-run known-working titles against new releases to catch regressions.

**Release gate:** A maintained compatibility catalogue and regression suite demonstrate broad, reproducible testing; known compatibility limits are documented, not hidden.

## v0.8.0 — Experimental Expansion

**Goal:** Explore harder engine families without destabilizing supported paths.

- Investigate XNA, FNA and MonoGame and determine where ARM64 runtime replacement is feasible.
- Prototype managed-assembly detection and native dependency analysis.
- Research Unity Mono portability, IL2CPP limitations, engine binaries, plugins and VR/OpenXR constraints.
- Keep speculative backends behind explicit experimental gates.
- Write technical feasibility assessments when a dependable generic conversion path cannot be established.

**Release gate:** At least one isolated new-engine proof of concept or a documented technical assessment of what prevents practical support. No experimental backend is advertised as stable merely because a prototype boots.

## v0.9.0 — Public Beta

**Goal:** Make the converter usable by people who did not develop it.

- Publish verifiable application builds and practical Windows/Linux installation instructions.
- Polish unified GUI conversion, library, settings and diagnostics flows.
- Provide progress reporting, actionable errors and easy export of opt-in diagnostic reports.
- Test clean installations without developer toolchains.
- Automate builds, package verification and regression CI.
- Document supported engines, exact limitations, compatible devices and troubleshooting.
- Audit licensing, attribution, dependency verification, source integrity and safe file handling.
- Address release-blocking issues raised by external testers.

**Release gate:** Independent testers complete documented conversion-to-device workflows without developer intervention; no known critical data-loss or destructive-source-file defects remain.

## v1.0.0 — Stable Release

**Goal:** Deliver a trustworthy, extensible Linux ARM64 game conversion platform.

- Consistent GUI and CLI for all advertised stable backends.
- Reproducible engine/version detection, runtime selection and native packaging.
- Reliable source preservation and explicit handling of unsupported games.
- Safe compatibility recipes, versioned package manifests and stable backend contracts.
- Verified Steam Frame deployment plus portable offline archives.
- Public, evidence-based game compatibility catalogue.
- Automated regression and release processes.
- Complete user and contributor documentation.

**Release gate:** All documented stable workflows work reliably on clean supported systems, with no critical unresolved packaging or source-integrity defects. **1.0 means a stable converter for supported games, not universal compatibility.**

---

## Beyond 1.0 (candidates, not commitments)

- Broader Unity conversion research, including VR titles.
- Additional small and open game engines.
- More ARM64 Linux devices and distributions.
- Community-maintained compatibility recipes and reports.
- Android portability for selected compatible engines.
- Performance analysis and automated optimization profiles.

## Project-wide rules

1. **Never modify source installations.** Work from a separate copy/output.
2. **Never redistribute game files.** Users provide their own legally obtained installations.
3. **Fix engine and platform problems first.** A specific game is a test case, not the architectural unit.
4. **Report evidence precisely.** Builds, Launches, Playable and Fully Tested are different claims.
5. **Be honest about native execution.** Distinguish ARM64 binaries from x86 translation/emulation.
6. **Keep experimental work isolated.** New engines must not destabilize supported backends.
7. **Protect working games.** Maintain regression tests as the framework grows.
8. **Keep the CLI first-class.** GUI conveniences must not break headless and scripted use.

## Release management

Version milestones are **scope targets**, not release dates. Features can move if hardware testing, licensing or compatibility constraints demand it. A release is complete only when its acceptance criteria and regression checks pass.

### Fine-grained versioning and traceable ZIP output

After the v0.1.0 candidate's existing-game regression retest, establish a single authoritative application version and **four-component** release identifiers for subsequent revisions: `MAJOR.MINOR.PATCH.REVISION`. Keep `0.1.0` as the initial baseline; use `0.1.0.1`, `0.1.0.2`, etc. for tightly scoped follow-up releases. Larger planned releases can use identifiers such as `0.1.1.0` and `0.2.0.0`. Increment versions deliberately for published changes, not on every developer build; record the Git commit separately for exact traceability.

- Name packaged Windows releases `multi-engine-game-conversion-framework-by-tovakai-v<version>-windows-x64.zip` (and version any future application release archives).
- Name **all** converted-game ZIPs `<game>-frame-conv-v<version>-linux-aarch64.zip` or an equivalent sanitized, clearly labeled convention; the embedded version means **converter version**, not source-game version. Preserve the `-linux-aarch64.zip` suffix for existing distribution/install consumers.
- Include converter version and source Git commit in portable game metadata/manifests and application build metadata. Preserve source-game version as an independent field.
- Use the same version source in GUI About/status, CLI `--version`, package metadata and build scripts. Do not hardcode conflicting versions across backends.
- Handle old unversioned ZIPs gracefully and never silently overwrite a different release's package. Update packaging, repackage/artwork commands, Frame installation/manifests, and automated tests together.
- **Do not change the converter code or release version during the immediate working-main regression retest.** Implement this versioning policy after recording those results, then test clean builds and all backend ZIP names before release.
