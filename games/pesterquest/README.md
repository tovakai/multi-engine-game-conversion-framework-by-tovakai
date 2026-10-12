# Pesterquest

| Field | v0.1.0.3 compatibility record |
| --- | --- |
| Game edition | Ren'Py 7.3.5 source → 7.5.0 ARM64 runtime |
| Backend | RenFrame (legacy engine migration) |
| Target | Native Linux ARM64 |
| Tested device | Steam Frame |
| Hardware status | **Playable (early story and save/load)** |
| Workflow | Opt-in, guarded full-engine migration |

## Observed behavior

Stages A/B confirmed on Steam Frame: menu, audio, controls, route selection, dialogue, choices, save/load and correct progress restoration after native Steam relaunch.

## Scope and limitations

Several volumes, unusual transitions, deeper persistence and Steam hooks remain unverified. This is a catalog snapshot **against release v0.1.0.3**, not a claim of a fresh v0.1.0.3 retest unless specifically noted.

## Sources

[Migration and hardware test](../../docs/renpy-735-arm64-migration.md)

[← Full compatibility index](../README.md)
