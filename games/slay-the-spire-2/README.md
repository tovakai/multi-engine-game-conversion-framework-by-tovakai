# Slay the Spire 2

| Field | v0.1.0.3 compatibility record |
| --- | --- |
| Game edition | Pinned supported edition; exact hardware-report build not recorded |
| Backend | Experimental STS2 (.NET) |
| Target | Native Linux ARM64 after device-side build |
| Tested device | Steam Frame |
| Hardware status | **Reported working (test depth unspecified)** |
| Conversion workflow | **Two-stage:** Windows creates transfer ZIP; Steam Frame runs installer to build final native components |

## Observed behavior

Listed among 23 user-reported working Steam Frame packages. A successful two-stage workflow is not the same as one-click conversion.

## Scope and limitations

Requires user-provided FMOD Studio API 2.03.15 Linux SDK, a supported installed Steam game and Frame-side build prerequisites. Multiplayer/extended testing unverified.

This entry describes **evidence available when converter v0.1.0.3 shipped**. Earlier game tests were not necessarily repeated against the exact v0.1.0.3 binary. Successful detection or packaging alone is not a gameplay pass.

## Sources

[Hardware report](../../docs/hardware-feedback-2026-10-11.md) · [Two-stage workflow](../../docs/sts2-integrated-workflow.md) · [v0.1.0.3 release](../../docs/releases/0.1.0.3.md)

[← Full compatibility index](../README.md)
