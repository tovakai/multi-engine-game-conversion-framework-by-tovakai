# Celeste

| Field | v0.1.0.3 compatibility record |
| --- | --- |
| Game edition | Vanilla Steam Windows XNA 1.4.0.0 |
| Backend | CelesteFrame (XNA → FNA) |
| Target | Native Linux ARM64 |
| Tested device | Steam Frame |
| Hardware status | **Playable (movement and save/load confirmed)** |
| Conversion workflow | Standard converter ZIP; owner supplies verified FMOD Linux SDK |

## Observed behavior

Frame gameplay confirmed movement, jumping, climbing, dashing, music, controller support and save/load after Steam relaunch. External 8BitDo input also worked.

## Scope and limitations

**FMOD Studio API 2.03.15 Linux SDK** must be obtained separately. Exact tested Steam XNA edition only; Everest, other versions, achievements, Steam Cloud and full completion unverified. Steam controller order matters.

This entry describes **evidence available when converter v0.1.0.3 shipped**. Earlier game tests were not necessarily repeated against the exact v0.1.0.3 binary. Successful detection or packaging alone is not a gameplay pass.

## Sources

[CelesteFrame setup and validation](../../docs/backends/celesteframe.md) · [Release notes](../../docs/releases/0.1.0.2.md) · [v0.1.0.3 FMOD guide](../../docs/releases/0.1.0.3.md)

[← Full compatibility index](../README.md)
