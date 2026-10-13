# FrameBench Stardew Valley protocol

**Protocol id:** `framebench-stardew-413150-v1`  
**AppID:** 413150  
**Variants:** native ARM64 MonoFrame package · original Steam Linux x86/FEX  
**Evidence class:** hardware observations only after on-Frame execution. pytest coverage of this protocol is simulated.

## Scene

Title-menu idle, or the same farm/map tile if a save is loaded. Do not change
in-game settings, mods, zoom or vsync between variants.

## Conditions (required or strongly recommended)

- Battery-powered, unplugged. If charging, the run is labeled and battery figures are not compared.
- Same headset brightness, refresh rate and FPS cap.
- Same SteamOS performance/power profile.
- Same tracking, passthrough and Wi-Fi.
- Similar charge percentage and thermals.
- 20 s warm-up, then 180 s scored samples at 1 Hz.
- Alternate native / original / native / original.
- Launch both through the real Steam AppID 413150 entry. No desktop-to-VR command copying. No Steam restart.

## Procedure

1. `framebench detect-sensors` — confirm `vph` and `max1720x`.
2. Select the converted MonoFrame package.
3. GUI: choose **Native ARM64**, start. FrameBench installs the dual-mode wrapper, launches Steam, verifies AArch64 without FEX, records, restores.
4. Choose **Original Steam**, start. Verify FEX or x86_64 in the process chain before scoring.
5. Open the HTML report. Endurance values are estimates.

Refuse to start if the running process does not match the requested mode.
Refuse to switch while the game is already running.
If the GUI crashes, `framebench recover --consent` restores the journal.

## What to record

Mean/median/peak system power, battery discharge, integrated Wh, Wh per minute,
estimated endurance (labeled), CPU/GPU rails, FPS/frame time when available,
CPU and RSS, condition metadata, architecture verification, simulated-vs-hardware flag.
