# Steam Artwork Companion

A standalone GUI for assigning local PNG/JPEG artwork to existing non-Steam
entries on the Steam Frame. It does not require a converted game, package
metadata, the converter GUI or Steam's debugger. Local images work offline;
SteamGridDB fetching is optional and requires your own API key.
Entries added manually through Steam or through other tools are supported when
they are saved in the selected Steam profile's `shortcuts.vdf`.

## Use

Run the companion in the Frame desktop session:

1. Choose the Steam profile and select an entry. Search by name or AppID;
   duplicate names remain distinguishable by their IDs and executable paths.
2. Browse separately for portrait grid, landscape grid, hero banner and logo.
   Existing and selected artwork have previews. **Keep current** discards a
   pending selection without removing existing artwork.
3. Exit Steam fully, then click **Apply artwork**. Reopen Steam to reload images.

Alternatively, enter a SteamGridDB API key and the numeric ID from
`https://www.steamgriddb.com/game/ID`, then click **Fetch artwork**. This is a
SteamGridDB game ID, not the Steam AppID or shortcut ID. The matched game name
is shown after fetching. The companion chooses highly scored static images,
stages them in temporary storage and fills only slots without a pending image
selection. Fetching never applies images to Steam automatically. Review the
previews and replace any slot with a local image before Apply. Missing artwork
is reported without discarding successful downloads.

Get a key from [SteamGridDB API preferences](https://www.steamgriddb.com/profile/preferences/api).
The masked key is kept in memory for the session; it is not saved in settings,
backups or downloaded files. Downloads use the
[SteamGridDB API v2](https://www.steamgriddb.com/api/v2). Lookup defaults to
static, non-NSFW artwork without humor or epilepsy tags. No key is needed for
local browsing or applying already selected images.

Unselected slots stay unchanged. Suggested dimensions are hints, not mandatory
sizes. Transparent PNG works well for logos. This version edits these four
library artwork types; shortcut executable icons and logo positioning are
separate Steam settings.

The app discovers native and Flatpak Steam profiles. If needed, browse to
`<Steam>/userdata/<account-number>` manually. It uses the AppID stored in the
shortcut, including unsigned conversion of binary 32-bit IDs, rather than
recomputing an ID from a name or requiring our installer.

## Run from source

Requires Python 3.10+, Tkinter and Pillow. On the Frame, use a Python installation
with Tk support; this does not require changing SteamOS's read-only system.
From a checkout:

```bash
python3 -m venv .venv-artwork
.venv-artwork/bin/python -m pip install -e '.[artwork-gui]'
.venv-artwork/bin/python -m steamartwork
```

Installation also provides the `steam-artwork-companion` command. The
`steamartwork` package imports no game-conversion modules and can be copied and
run independently with Python, Tkinter and Pillow.

## Standalone binary

Build on Linux ARM64 with Tkinter available:

```bash
.venv-artwork/bin/python -m pip install pyinstaller
ARTWORK_PYTHON=.venv-artwork/bin/python bash scripts/build-steam-artwork.sh
```

The 0.1.1.1 native ARM64 converter archive includes the standalone companion in
its `Steam Artwork Companion` subfolder. Copy that whole subfolder to the Frame
if only the companion is wanted. Windows/Linux x64 converter archives do not
include a Frame executable. It remains independent of the converter.

When building separately, copy the entire `dist/steam-artwork-companion`
directory to the Frame and run its
`steam-artwork-companion` executable. A build made on x86 Linux is not an ARM64
binary. The companion has its own entry point and build script; building the
native ARM64 converter build now also produces it; other platform builds do not.

## Backups and recovery

Shortcut files, launch options and game data are never rewritten. Apply
validates all selected images before making changes, creates a recovery record,
then replaces artwork files under the selected profile's `config/grid`.
Other PNG/JPEG variants of each selected slot are backed up and removed to avoid
Steam choosing an older variant. Each image replacement uses an atomic rename;
a failed operation attempts to roll back all selected slots.

Backups live in `config/artwork-companion-backups/<operation-id>` beside the
Steam profile's other configuration. The success message gives the exact path.
**Undo last apply** restores the last operation during the current session and
refuses to overwrite artwork subsequently changed by another application.
Backups remain on disk after closing the app.

For manual recovery with Steam closed, inspect a backup's `manifest.json`.
For each filename in `before`, restore the saved file to `config/grid` when the
value is `true`; remove the corresponding grid file when it is `false`.
The manifest lists only the affected artwork variants. Retain backups until
the result has been checked in Steam. A persistent storage failure can prevent
automatic rollback; use those backups once storage is working again.

## Verification scope

Automated tests use isolated synthetic Steam profiles and real images. They
cover binary shortcut parsing, unsigned IDs, profile discovery, unrelated data
preservation, format validation, backups, rollback, stale entries, symbolic
links and Undo conflict detection. Hardware/UI observations should be recorded
separately; passing these tests does not establish a Steam UI refresh result.

On 2026-10-15, 31 companion tests passed on the physical ARM64 Frame using a
virtual X display and isolated synthetic Steam profiles. The GUI test exercised
local browsing, a mocked SteamGridDB fetch, mixed selections, Apply and Undo.
Read-only discovery parsed one actual Steam profile containing 16 saved
non-Steam entries. The standalone ARM64 binary also opened successfully without
the temporary Python/Tcl/Tk environment overrides. No actual library artwork was
changed by these checks. Live authenticated SteamGridDB fetching and artwork
appearance after a real Steam restart remain unverified.

The source checkout's local companion and existing artwork regression checks
passed 53 tests; the GUI test was skipped locally because no display was
available. It ran successfully on the Frame as described above.
