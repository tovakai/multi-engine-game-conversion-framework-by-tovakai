# Roadmap: from proof of concept to dependable ARM64 conversions

**Project:** Multi-Engine Game Conversion Framework by tovakai  
**Reference device:** Steam Frame  
**Output goal:** native Linux AArch64 game packages  
**Last revised:** 2026-10-12

> This is a living plan, not a list of engines that must be invented in a particular version or a promise of dates. The next release is **v0.1.1: stability testing**. Beyond that, milestones can change when real hardware evidence changes our priorities.

## Mission and current position

Let people provide their own legally obtained games, detect compatible engine/runtime requirements, and produce portable native Linux AArch64 packages while leaving original installations untouched. Prefer reusable engine and platform compatibility work over game-specific hacks, and be exact about what has actually been verified.

**v0.1.0, Foundation, shipped on 2026-10-12.** It includes a unified Windows x64 / Linux ARM64 GUI and CLI, verified runtime downloads, native game ZIP packaging, and a Steam Frame install workflow.

Several capabilities arrived earlier than the original roadmap predicted:

- **RenFrame:** supported Ren'Py 7/8 paths plus explicitly approved legacy migrations.
- **RPGMFrame:** supported RPG Maker and Godot paths, including specialized GodotSteam recipes.
- **Experimental backends:** GameMakerFrame, ConstructFrame, LÖVEFrame, AGSFrame, and MonoFrame already exist; they are not blanket support for their entire engine families.
- **Experimental STS2:** a separate two-stage device-finishing workflow, not the standard one-step game conversion path.

The [2026-10-11 Steam Frame report](hardware-feedback-2026-10-11.md) lists **23 user-reported working game packages**. That is excellent feasibility evidence, but not 23 independent end-to-end conversions re-tested from the **tagged 0.1.0 application build**, and not 23 full-game certifications. The distinction drives our next steps.

## Release outlook

| Milestone | Focus | Practical outcome |
| --- | --- | --- |
| **v0.1.0** (released) | Foundation | Downloadable converter, core routing, native packaging, runtime provenance |
| **v0.1.1** (next) | **Stability and regression testing** | Confirm the actual release-style workflow works repeatedly, catch regressions, document limits |
| **v0.1.x** (as needed) | Maintenance | Small high-confidence bug, security, packaging, and compatibility fixes |
| **v0.2.0** (candidate) | Reproducible conversions and coverage | A repeatable GUI-to-Frame experience for reference games and a documented 35-title test matrix |
| **Later milestones** | Compatibility infrastructure, deployment, mods/saves, broader ARM64 devices | Prioritized from test evidence rather than assigned rigid version numbers prematurely |
| **v1.0.0** (long-term) | Stable supported workflows | Reliable, documented conversions for a declared scope, **not** every game on every engine |

---

## v0.1.1: Stability first

**Intent:** Test what we shipped. Avoid major architecture changes or adding engines just to raise the backend count.

### Test the user journey, not only the runtime

- Start with **clean, released-style Windows x64 and Linux ARM64 application archives**; verify extraction, frozen GUI startup, CLI entry points, dependencies, notices, architectures, and checksum/provenance metadata.
- Exercise **GUI selection/drop → correct inspection → runtime resolution/download → conversion → Linux ARM64 game ZIP → transfer/extract → native launch or Steam Frame install**.
- Repeat representative conversions with **empty and warm runtime caches**. Test missing/corrupt downloads, offline behavior where supported, paths with spaces/non-ASCII characters, ZIP extraction, and permissions.
- Confirm **source files and installations remain unchanged**. Ensure output manifests describe the actual source game, selected ARM64 runtime, applied migration, converter version, and source commit without bundling user secrets or game files in any public artifact.
- On real hardware, distinguish **launch/menu**, **input**, **short gameplay**, **save/load**, **quit/relaunch**, and **longer gameplay** as separate checkpoints. Test Steam Input through a real Steam shortcut instead of assuming a controller device is exposed to ordinary Linux processes.
- Retest a **representative subset** of the existing working catalogue with packages produced by the release candidate, and log any difference from earlier manually tuned builds. The existing 23 reports are a starting point, **not a mandatory full 23-game certification gate**.
- Cover representative supported Ren'Py 7/8, legacy migration, RPG Maker, and Godot paths, plus sample existing experimental backends where inputs/dependencies are available. Test the pinned Stardew Valley profile and two-stage STS2 as **separate** scoped paths; do not mark the normal one-step converter broken because a documented experimental backend requires extra steps.
- Convert repeated crashes, packaging errors, missing assets, controller regressions, and runtime-resolution failures into reproducible tests and clear issue reports.

### Fix in priority order

1. **Release blockers:** source mutation/data loss, unsafe extraction, compromised provenance or checksum handling, broken published application archives, or a regression in a previously supported conversion path.
2. **High-value stability bugs:** GUI crashes, stale/corrupt caches, non-reproducible game ZIPs, installer/launcher failures, save/load regression, misleading error messages.
3. **Documented limitations:** title-dependent performance, input, graphics, native plugins, online play, and unusually version-sensitive migrations. Fix them when evidence supports a contained change; do not turn this patch into an expansion milestone.

The known Cassette Beasts rendering/input issues, Cook, Serve, Delicious! 3 performance/input issues, Desert Child graphics issues, and partial certification of legacy Ren'Py/STS2 are **not silently reclassified as solved**.

**Release gate for v0.1.1:** Windows and native ARM64 build/startup checks and regression CI pass; clean-cache and cached-path end-to-end conversion/packaging checks pass on representative games; at least a scoped set of fresh Steam Frame gameplay/input/save/relaunch results is recorded; serious newly identified release blockers are resolved; known experimental limitations are clearly listed. Do not delay this maintenance release merely to finish every unsupported game or complete a 23-title playthrough.

## v0.2.0: Make successful conversions reproducible

**Intent:** The application should recreate what an expert got working manually, without rediscovering game-specific fixes in a terminal every time.

- Maintain the existing **35-distinct-title coverage target** as a testing matrix: **20 Ren'Py**, **10 RPG Maker** across its major generations, and **5 Godot**. Count reported failures as *tested* when diagnosis/reproduction is recorded; do not call them *playable*.
- Record source game version, source engine version, converter version/commit, selected ARM64 runtime, migration or recipe, target device, GUI/CLI conversion outcome, native launch, input, gameplay, save/load, and known caveats.
- Prioritize the gap between **working manually patched prototypes** and **repeatable conversions from an original user-supplied installation**. STS2 is an important case, but retain its separately documented two-stage installation requirements until that route is genuinely simplified.
- Increase depth for existing GameMaker, LÖVE, Construct, AGS, MonoGame/.NET and custom Godot cases **before** advertising broad support for additional engines. Verify what the app can reproduce, not just what has booted once.
- Keep runtime pins and checksums, game-version recognition, compatibility recipes, build manifests, and regression fixtures in sync. Prefer common backend/platform fixes; use exact, opt-in title/version profiles when genuinely required.
- Treat controller mapping and native rendering as compatibility test dimensions. A title-screen screenshot alone does not establish success.

**Candidate release gate:** A published compatibility matrix for the 35 requested title tests, backed by repeatable conversion evidence for representative supported engines; working reference games can be rebuilt through the actual public interface without manual patching of output files. This is **not** a guarantee of 35 playable games.

## Next, without premature version numbers

The following are **workstreams**, not a fixed 0.3.0–0.9.0 calendar. Choose among them once stability and conversion reproducibility tell us where the biggest problems are.

| Workstream | Why it matters |
| --- | --- |
| **Compatibility recipes and diagnostics** | Improve the existing engine/version detection and pinned recipes; add safe, version-scoped repairs, portable diagnostic bundles, and regression tracking rather than repeating investigative work title by title. |
| **Older Ren'Py games** | Expand RenFrame's coverage of legacy Ren'Py releases (especially 6.x and early 7.x, with older generations assessed separately). Prioritize safe detection, compatible Python 2 ARM64 runtime/migration paths, script/bytecode compatibility, media and saves; reuse existing narrow migration profiles instead of silently upgrading incompatible projects. |
| **Steam Frame and device integration** | Improve transfer, install, repair, uninstall, artwork, and controller guidance. Aim for a non-terminal path where feasible without making SSH, Steam settings changes, or online access mandatory. |
| **Device-side finalization** | Generalize the experimental STS2-style two-stage contract for engines requiring native components, vendor SDKs, or final ARM64 builds; keep licensing and ownership boundaries intact. |
| **Mods, saves, and libraries** | Revisit the existing Ren'Py mod-library prototype; offer reversible profiles, save-location discovery/migration, and clear handling of native x86-only mod dependencies. |
| **Broader ARM64 Linux hardware** | Move beyond a single Steam Frame baseline to handhelds, laptops, and low-power boards where games are viable; measure performance and memory honestly rather than assuming native automatically means faster. |
| **New engine research** | Investigate XNA/FNA/MonoGame generalization, Unity/VR, WOLF RPG Editor, and other candidates only behind explicit experimental scopes. MonoFrame already exists for one pinned Stardew Valley version; that does **not** imply general managed-game compatibility. |
| **Community verification** | Build a useful compatibility catalogue, reproducible issue templates, opt-in diagnostics, contributor docs, and clear distinctions between reported working, reproducibly converted, and fully played. |

## Older Ren'Py compatibility: dedicated research and implementation track

**Goal:** Bring more games built with pre-ARM64 Ren'Py releases to native Linux AArch64 without treating a single successful migration as proof of universal legacy support.

- **Inventory legacy generations:** Map relevant Ren'Py 6.x and pre-7.5 7.x releases, then investigate even older releases (including 5.x) separately where practical. Record each game's exact engine version, Python generation, archives, bytecode-only scripts, extensions, and external binaries.
- **Build on existing evidence:** Preserve the narrowly scoped experimental paths for original **DDLC 6.99.12 → 7.5.3** and **Ren'Py 7.3.5 / 7.4.x → 7.5.0**, plus existing title-specific Katawa Shoujo compatibility research. These are starting points, **not generic support for all 6.x or early 7.x games**.
- **Choose safe strategies per generation:** Evaluate full-engine migration, source/script transformation, or independently maintained compatible ARM64 runtimes as appropriate. Respect Python 2 vs Python 3, engine APIs, compiled bytecode formats, Python/native extensions, codecs, shaders, and other dependencies. Avoid mixing incompatible engine code with native runtime libraries.
- **Keep migration explicit and reversible:** Detect unsupported combinations clearly; require opt-in for cross-version migrations; always preserve the source game. Do not guess a nearby engine release or distribute retail assets or proprietary binaries.
- **Verify more than startup:** Test dialogue, choices, image/audio/video, rollback, save/load, exit/relaunch, and where relevant script/character-file behavior on actual ARM64 hardware. Add version-scoped automated fixtures and record regressions separately from game-specific failures.

**Success criterion:** More independently tested legacy Ren'Py versions can be **reproducibly converted through the public application** using documented, narrowly scoped compatibility paths. This work is prioritized after the immediate v0.1.1 stability pass unless a contained regression fix belongs in that patch; no new blanket legacy-support promise is implied.

## What v1.0 would actually mean

A stable converter for **explicitly supported engine/game-version combinations**, not universal compatibility. The bar should be:

- The published GUI and CLI consistently inspect, convert, package, and report errors for the documented supported scope.
- Supported reference builds reproduce on clean hosts, using verified dependencies and traceable artifacts, without unpublished manual intervention.
- Original game data remains untouched. The project never distributes users' games or unlicensed proprietary SDKs.
- Installation and launch are documented and tested on specified ARM64 Linux targets, with known controller, graphics, online, and save limitations disclosed.
- Regression tests, hardware reports, compatibility status definitions, release provenance, and security fixes are maintained well enough for outside users and contributors to trust the result.

**Being public is not the same as being stable.** v0.1.0 is already a public release; v1.0 is a quality threshold rather than a future download button.

---

## Project-wide engineering rules

1. **Preserve sources.** Never modify the input game installation; work in independent outputs and verify preservation.
2. **No game redistribution.** Users provide their own acquired files; vendor SDKs and Steam client binaries remain separately licensed.
3. **Exactness beats guesswork.** Do not substitute engine versions, libraries, or migration paths silently. Validate compatibility and require approval for experimental cross-version changes.
4. **Support claims require evidence.** Keep **Detected**, **Built**, **Launches**, **Playable**, **Reproducibly Converted**, and **Deeper Tested** distinct. A failure that is carefully diagnosed still counts toward test coverage.
5. **Native means native.** Report when ARM64 execution is real and when compatibility/translation or special Steam context is still involved.
6. **Fix common problems first.** Prefer engine/platform repairs over per-title branches; keep exceptional title/version profiles narrowly bounded.
7. **Keep experiments isolated.** Protect working paths, treat regression tests as release gates, and never force experimental dependencies on unrelated backends.
8. **CLI is first-class.** GUI improvements cannot remove headless/scripted compatibility.
9. **Small releases beat imaginary milestones.** Ship scoped fixes when verified; rewrite upcoming priorities when results justify it.

## Versioning and release traceability

- Keep **v0.1.0** as the immutable tagged foundation baseline. Plan the next normal maintenance release as **v0.1.1**; use further `0.1.x` releases as needed, not as feature-count targets.
- Keep the application version consistent across GUI/CLI/package metadata, `pyproject.toml`, release assets, and converted-game manifests. Record the **full commit hash** independently for exact provenance.
- Include **converter version** in generated game ZIP naming and metadata, separately from the source game's version. Maintain backward compatibility with old package names and installation scripts.
- The earlier **four-component micro-revision** idea (`0.1.1.1`, `0.1.1.2`) remains an optional policy to implement consistently if useful. Do not promise that format until release tooling, version parsing, artifact names, and tests all support it.
- Publish application releases separately from checksum-pinned runtime bundles. Verified CI builds and archive checks are necessary, but never a substitute for real-device acceptance.
- Keep release notes honest about experimental workflows and open defects; no schedule or version number automatically elevates an entire engine family to stable support.

See [release process](release-process.md), [v0.1.0 scope](releases/0.1.0.md), [hardware feedback](hardware-feedback-2026-10-11.md), and [MonoFrame validation](monoframe.md).
