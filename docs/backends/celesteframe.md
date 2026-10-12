# CelesteFrame

CelesteFrame converts the verified vanilla Steam **Windows XNA Celeste 1.4.0.0**
installation into a native Linux ARM64 FNA package for Steam Frame. It preserves
the owned game content and prepares a separate managed executable. It uses real
Steam initialization and stats interfaces through the Frame's installed client.

The converter automatically downloads and verifies the matching Celeste runtime
SDK. Supply the separately obtained **FMOD Studio API 2.03.15 Linux SDK** archive.
The open runtime SDK includes
FNA 23.10, FNA3D, FAudio, Theorafile, SDL2, .NET 8.0.31 and preparation tools;
it excludes game data, FMOD libraries and Steam client libraries.

```powershell
python -m megcfbt build "C:\Program Files (x86)\Steam\steamapps\common\Celeste" `
  --fmod-sdk "C:\path\to\fmodstudioapi20315linux.tar.gz" `
  --output "C:\Conversions\Celeste-frame"
```

The GUI detects Celeste, selects the runtime automatically, and finds the FMOD
archive in Downloads or lets you select it. `--runtime` can select an optional
matching runtime directory override. `MEGCFBT_CELESTE_FMOD_SDK` can
also select the archive. FMOD SDK archives with an unexpected checksum are
rejected. The original installation and its saves remain untouched; an existing
source `Saves/` directory is copied into the new package.

Transfer and extract the generated ZIP, run `install-to-steam.sh` with Steam
running, and launch the new **Celeste** shortcut. Steam launch provides the input
and display context needed on Frame. When multiple controllers are connected,
choose the desired primary controller using Steam's controller order settings.
The game retains its existing primary-controller selection behavior.

## Validation and limits

The owner confirmed menu, music, movement, jumping, climbing, dashing and save
loading after relaunch with the Frame controllers. An external 8BitDo gamepad
also worked. Process mappings and ELF checks confirm the ARM64 runtime, graphics,
audio and real Valve Steam API. Normal Windows CLI conversion and the generated
ZIP's Steam installer were exercised on the owned installation.

Everest, mods, the FNA/openGL beta branch and other Celeste releases need their
own profiles. Full-game completion, achievements and Steam Cloud are unverified.
See [the hardware record](../../celesteframe/validation-2026-10-12.json) and
[the SDK source recipe](../../experiments/celeste/README.md).
