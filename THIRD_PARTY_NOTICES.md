# Third-party notices

## Official Ren'Py compatibility SDK

The experimental original DDLC 1.1.1 migration downloads the official Ren'Py
7.5.3 ARM SDK locally from https://www.renpy.org/release/7.5.3 and verifies its
SHA256 before selecting the matched Python 2 engine and AArch64 runtime.
Ren'Py's `LICENSE.txt` and `doc/license.html` notices are retained in that
output. See https://www.renpy.org/doc/html/license.html for component licenses
and upstream source links. The converter repository does not bundle the SDK
or any original DDLC assets/scripts. No code from DDLC-ARM-Linux, PortMaster,
decompiled DDLC repositories or mod templates was copied.

## Legacy compatibility profiles

The recovered Katawa Shoujo compatibility profile downloads the pinned community
Ren'Py 8 port at https://github.com/gcammisa/KatawaShoujo-RenPy8/releases/tag/8.0.3
and HD UI/source overrides from https://github.com/scoopgoop/Katawa-Shoujo-HD-Upscale
at commit `ef24235c4ae6f9c67e371cfd79446cff2c02f3f8`. These are fetched locally
and combined with the user's installation. No game payloads are bundled in this
repository. The generated `RENFRAME-COMPATIBILITY.txt` records these sources.

EasyRPG packages depend on the separately installed native EasyRPG Player:
https://github.com/EasyRPG/Player (GPL-3.0-or-later). Its binaries are not bundled
in the converter. The native Flatpak installation supplies its component notices.

## Deckport

The Steam Frame non-Steam shortcut installer adapts Deckport's deterministic
non-Steam AppID calculation, binary `shortcuts.vdf` handling, and Steam artwork
filename convention.

Project: https://github.com/wesellis/deckport

MIT License

Copyright (c) 2026 Wesley Ellis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
