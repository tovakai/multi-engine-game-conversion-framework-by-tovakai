# Hollow Knight

| Field | v0.1.0.3 compatibility record |
| --- | --- |
| Game edition | Steam Windows edition, Unity 6000.0.61f1 |
| Backend | UnityFrame (exact Unity Mono profile) |
| Target | **Windows ARM64 under ARM64 Proton**, not Linux ELF |
| Tested device | Steam Frame |
| Hardware status | **Playable (early controller gameplay + save/load)** |
| Conversion workflow | Standard converter GUI/CLI for exact vetted source; outputs `*-windows-arm64-proton.zip` |

## Observed behavior

Frame controller menu/gameplay, movement/jumping, audio, bench saving and successful Continue after relaunch confirmed. GUI package installed via Steam.

## Scope and limitations

Requires supported **ARM64 Proton 11.0** and exact tested vanilla assemblies/plugins; other Unity versions/IL2CPP and mods unsupported. Longer gameplay, vibration, hotplug and achievements unverified.

This entry describes **evidence available when converter v0.1.0.3 shipped**. Earlier game tests were not necessarily repeated against the exact v0.1.0.3 binary. Successful detection or packaging alone is not a gameplay pass.

## Sources

[UnityFrame setup](../../docs/backends/unityframe.md) · [v0.1.0.1 release](../../docs/releases/0.1.0.1.md) · [v0.1.0.3 retention](../../docs/releases/0.1.0.3.md)

[← Full compatibility index](../README.md)
