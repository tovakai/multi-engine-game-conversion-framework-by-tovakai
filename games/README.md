# Game compatibility catalog

**Scope: Multi-Engine Game Conversion Framework by tovakai v0.1.0.3 (2026-10-13).**

This is the **full recorded game-test index** for the v0.1.0.3 documentation snapshot. Each game has its own folder and `README.md`, PortMaster-style, so future testing, version-specific notes, screenshots or compatibility recipes have a stable home. All recorded statuses are based on actual project evidence, not predictions from engine detection. There are **36 indexed game entries** here; variants of the same title may be documented in one folder or in separate folders where the source editions differ (for example, Katawa Shoujo vs HD).

The **23-package Steam Frame report is dated 2026-10-11**; it is historical hardware feedback, **not a fresh 0.1.0.3 retest of every entry**. Celeste, Hollow Knight and Cassette Beasts have narrower, individually documented later hardware tests. The latest stable converter release is [v0.1.0.3](../docs/releases/0.1.0.3.md). The release archives contain the converter, not retail game files or third-party proprietary SDKs.

## Status guide

- **Playable:** Actual gameplay on ARM64 hardware confirmed, within the stated test depth. Not a certification of full completion.
- **Reported working:** User reported a working converted package on hardware; exact gameplay depth, package version or features may be unrecorded.
- **Launches:** Hardware startup/menu/intro confirmed, but sufficient gameplay not yet verified.
- **Issues:** Starts or plays, but has significant input, rendering or performance defects.
- **Needs retest:** Converter support changed after a previous problem, but no later passing hardware test is documented.

Conversion methods differ: nearly all results use native Linux AArch64 packages, but **Hollow Knight is Windows ARM64 under ARM64 Proton**, and **Slay the Spire 2 requires two-stage Frame-side installation/build**. The backend column identifies the reported route; a successful result for one edition does not imply support for every game update or every game made with that engine.

## All documented games

| Game | Backend | Hardware status | Important distinction |
| --- | --- | --- | --- |
| [A Date with Death](a-date-with-death/README.md) | RenFrame | Reported working | 2026-10-11 package report |
| [Alone with My Stepsister](alone-with-my-stepsister/README.md) | RenFrame | Needs retest | Nightly engine migration; no hardware gameplay evidence |
| [Balatro](balatro/README.md) | LÖVEFrame | Reported working | Hardware package report; LÖVE menu also tested |
| [Broken Sky](broken-sky/README.md) | RenFrame / Live2D | Launches | Notice screen after SDK provisioning; no gameplay |
| [Brotato](brotato/README.md) | Godot | Playable | Full run; pinned custom GodotSteam |
| [Cassette Beasts](cassette-beasts/README.md) | Godot / GodotSteam | Playable | 1.8.3 v0.1.0.3 rendering profile; controller unverified |
| [Celeste](celeste/README.md) | CelesteFrame / FNA | Playable | XNA 1.4.0.0; FMOD SDK needed; save/load and controls verified |
| [Cook, Serve, Delicious! 3](cook-serve-delicious-3/README.md) | GameMakerFrame | Issues | Lag and unreliable controller |
| [Desert Child](desert-child/README.md) | GameMakerFrame | Issues | Visible graphical glitches |
| [Doki Doki Literature Club!](doki-doki-literature-club/README.md) | RenFrame | Reported working | Original 1.1.1 only; later acts unverified |
| [Everlasting Summer](everlasting-summer/README.md) | RenFrame | Reported working | Original and separate beta have differing runtime profiles |
| [Fear & Hunger](fear-and-hunger/README.md) | RPGMFrame | Reported working | Hardware package report |
| [Fear & Hunger 2: TERMINA](fear-and-hunger-2-termina/README.md) | RPGMFrame | Reported working | Hardware package report |
| [Find Love or Die Trying](find-love-or-die-trying/README.md) | RenFrame | Reported working | Hardware package report |
| [Gravity Circuit](gravity-circuit/README.md) | LÖVEFrame | Launches | Language screen reached |
| [Grimm's Hollow](grimms-hollow/README.md) | RPGMFrame | Reported working | Hardware package report |
| [Help! I Married a Slut](help-i-married-a-slut/README.md) | RenFrame | Reported working | Hardware package report |
| [her tears were my light](her-tears-were-my-light/README.md) | RenFrame | Reported working | Hardware package report |
| [Hollow Knight](hollow-knight/README.md) | UnityFrame | Playable | Windows ARM64 under ARM64 Proton, not native Linux ELF |
| [Imperial Bureaucracy Hero](imperial-bureaucracy-hero/README.md) | Unrecorded | Reported working | Hardware package report |
| [Katawa Shoujo (non-HD)](katawa-shoujo/README.md) | RenFrame | Needs retest | Conversion profile repaired; hardware validation pending |
| [Katawa Shoujo HD](katawa-shoujo-hd/README.md) | RenFrame | Reported working | HD distribution, not the non-HD build |
| [Maya's Mission](mayas-mission/README.md) | Unrecorded | Reported working | Hardware package report |
| [Milk inside a bag of milk inside a bag of milk](milk-inside-a-bag-of-milk-inside-a-bag-of-milk/README.md) | RenFrame | Reported working | Native gameplay reported; exact runtime not logged |
| [My Pig Princess](my-pig-princess/README.md) | RenFrame | Reported working | 0.10.1 / Ren'Py 8.3.7 |
| [Pesterquest](pesterquest/README.md) | RenFrame | Playable | Opt-in 7.3.5→7.5.0 migration; save restoration tested |
| [Silly Linguine Cat Simulator Deluxe Online](silly-linguine-cat-simulator-deluxe-online/README.md) | Godot | Reported working | Online functionality unverified |
| [Slay the Spire 2](slay-the-spire-2/README.md) | Experimental STS2 | Reported working | **Two-stage Frame-side completion** |
| [Stardew Valley](stardew-valley/README.md) | MonoFrame | Playable | Exact 1.6.15; vanilla hash-verified profile |
| [The Cat Lady](the-cat-lady/README.md) | AGSFrame | Playable | Keyboard/mouse; controller not confirmed |
| [The Sea Wolves](the-sea-wolves/README.md) | Unrecorded | Reported working | Hardware package report |
| [The Witch's House](the-witchs-house/README.md) | Edition/backend unclear | Reported working | Hardware package report; separate menu-only test |
| [To the Moon](to-the-moon/README.md) | RPGMFrame | Reported working | Hardware package report |
| [Undertale](undertale/README.md) | GameMakerFrame | Playable | Early game through second savepoint and save/load |
| [Unnamed Space Idle](unnamed-space-idle/README.md) | Godot | Launches | Introduction reached |
| [Void Stranger](void-stranger/README.md) | GameMakerFrame | Reported working | Hardware package report |

## Adding or updating a game

1. Create `games/<lowercase-hyphenated-slug>/README.md` (one directory per game, with clearly separated edition-specific evidence). Use [the entry template](_template/README.md). Do not use a new folder for every converter build of the same title.
2. Record **source game version**, **backend and runtime**, **exact converter build/version**, **target hardware and graphics driver**, **packaging mode**, and **actual gameplay, save/load and input evidence**. State unknowns rather than guessing.
3. Link the new entry from this index and mark it *Playable* only if gameplay actually occurred. Keep separate evidence for historically reported working packages, main-menu tests, incomplete conversions and successful installs.
4. Open an [issue](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues) or PR with reproducible steps and sanitized logs. **Do not upload copyrighted game content, personal saves, vendor SDK binaries or converted game packages.**

Original baseline: [2026-10-11 user hardware report](../docs/hardware-feedback-2026-10-11.md). Backend- and game-specific evidence links are available on the individual pages.

[← Project README](../README.md)
