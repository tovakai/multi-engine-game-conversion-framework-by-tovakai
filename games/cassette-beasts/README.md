# Cassette Beasts

| Field | v0.1.0.3 compatibility record |
| --- | --- |
| Game edition | 1.8.3, identified Steam pack |
| Backend | Godot backend (Godot 3.5.1 / GodotSteam) |
| Target | Native Linux ARM64 |
| Tested device | Steam Frame |
| Hardware status | **Playable (five-minute test, battle and save/load)** |
| Conversion workflow | Standard v0.1.0.3 converter automatically applies narrow graphics profile |

## Observed behavior

User confirmed movement, area transition, tutorial battle and save/load on physical Steam Frame with no recurrence of disappearing tiles or flickering sprites. A fresh Windows-GUI-produced ZIP passed the same acceptance.

## Scope and limitations

**v0.1.0.3 fix:** GLES3 with `ZINK_DEBUG=norp` and forced depth pre-pass in PCK-adjacent `override.cfg`. Controller support remains unverified; other versions, drivers, full-game and online coverage have not been established.

This entry describes **evidence available when converter v0.1.0.3 shipped**. Earlier game tests were not necessarily repeated against the exact v0.1.0.3 binary. Successful detection or packaging alone is not a gameplay pass.

## Sources

[v0.1.0.3 release](../../docs/releases/0.1.0.3.md) · [Graphics investigation](../../docs/cassette-beasts-rendering.md)

[← Full compatibility index](../README.md)
