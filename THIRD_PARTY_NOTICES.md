# Third-party notices

## Hollow Knight ARM64 experiment

UnityFrame uses pefile 2024.8.26 (MIT, copyright 2004-2024 Ero Carrera) on the
conversion host for PE architecture, CLR and export inspection. Its license is
retained under `unityframe/licenses/pefile-MIT.txt` and included in the frozen
converter. Target-side verification uses only the Python standard library.

The experimental preparer uses the official Unity 6000.0.61f1 Windows ARM64 Mono
player from Unity's target-support package. It fetches no game assets and the
repository does not bundle the proprietary Unity runtime. The exact package
URL and locally verified component hashes are recorded in
`experiments/hollow-knight/profile.json`.

The xar/gzip/cpio format approach in `experiments/hollow-knight/unity_package.py`
is informed by DaVarga/bs-arm64's `tools/unity_pkg_extract.py`, pinned at
`5a318356703ac3835ee62bba677ba0778c76c7c5` (MIT, copyright 2026 Daniel Varga).
Its full notice is retained under
`experiments/hollow-knight/licenses/bs-arm64-MIT.txt`.

The preparer selects ARM64 graphics, Steam and runtime components from the
unmodified bs-arm64 v0.3.2 release. Component licenses and `SOURCES.md` are
retained in the owner's prepared output under `.hk-arm64/`; that source record
identifies the exact Proton, Wine, DXVK, Mono and toolchain sources and patches.
The repository does not bundle those downloaded binaries. The original game's
Steamworks.NET notice is also preserved in the copied installation.

Project: https://github.com/DaVarga/bs-arm64
Pinned release: https://github.com/DaVarga/bs-arm64/releases/tag/v0.3.2

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

## Native engine SDKs and Frame Steam helper

SDKs are built or selected separately and run as external processes. Game assets
are never bundled in this repository. The SDK producer retains upstream notices:

Published automatic native bundles retain component notices, source references
and build instructions. Butterscotch's argument validation patch is included.
Portable EasyRPG (GPL-3.0), liblcf and bundled LGPL dependencies have source
references; applicable dependency source archives and the GPL-2.0 TimGM6mb notice
accompany the bundle. No original RPG Maker RTP or proprietary Steam API binary
or SDK headers are published. LÖVE uses the Frame-installed native Steam API.

- Butterscotch: https://github.com/ButterscotchRunner/Butterscotch,
  AGPL-3.0. The bundled `ds_list_set` patch modifies argument validation; the
  pinned source commit and patch are recorded by the SDK recipe.
- LÖVE: https://github.com/love2d/love, zlib license.
- lua-https: https://github.com/love2d/lua-https, zlib license.
- luasteam: https://github.com/uspgamedev/luasteam, MIT license. The source
  recipe adapts the removed current-user stats request to the native API.
- Adventure Game Studio: https://github.com/adventuregamestudio/ags,
  Artistic License 2.0; component licenses remain applicable.
- GodotSteam: https://codeberg.org/godotsteam/godotsteam, MIT license, with
  Godot's MIT and component notices. The Godot 3.5.1 recipe restores its older
  dictionary initialization contract while preserving actual Steam results.

Steamworks libraries and headers retain Valve's applicable terms and are not
relicensed by this project. They are resolved from the selected upstream runtime
or the user's installation. The project-authored Frame graphics environment
helper is GPL-3.0, like the converter. Its C source, build recipe and checksum
receipt accompany the bundled ARM64 binary.

The Steam networking inline compatibility helpers follow the public
GameNetworkingSockets interface helpers:
https://github.com/ValveSoftware/GameNetworkingSockets

Copyright (c) 2018 Valve Corporation. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

# Integrated STS2 source backend

The software-only backend in `experiments/sts2-steamworks` is imported from the
working STS2 two-stage checkout and retains its AGPL v3 license in that directory.
The existing framework components retain their GPL v3 license. GPL v3 section 13
permits combination with AGPL v3 software; AGPL requirements apply to the combined
work. Both license texts must accompany combined distributions. This does not
license or redistribute retail game files, FMOD SDK inputs, or proprietary Steam
libraries. The backend includes its own dependency notices and redistribution
checks. Conversion uses the user's separately obtained, checksum-verified SDK.

## Optional Live2D runtime inputs

RenFrame can import Linux ARM64 Cubism Core from a user-downloaded Cubism SDK for
Native. The user must accept Live2D's agreements on its download page. The
converter application and public repository contain no Cubism Core binary or SDK.
Personal converted outputs include the selected library and its SDK license
notice. Live2D remains proprietary software under its vendor agreement; the
framework's GPL/AGPL licenses do not apply to it. Cached Core files are hashed and
architecture-checked before reuse. See https://www.live2d.com/en/sdk/download/native/.

## MonoFrame runtime SDK

The separately downloaded MonoFrame SDK includes Microsoft .NET 6.0.32 (MIT and
component notices), the patched MonoGame framework (Ms-PL), the mainline Stardew
preparation tool (MIT), Mono.Cecil (MIT), NVorbis (MIT), STB image helpers (public
domain), controller mapping data, and SkiaSharp with its component notices.
The SDK contains license texts, source revision links and compatibility patch
source. See [MonoFrame provenance](docs/monoframe.md).

The Frame graphics guard and legacy Steam API bridge are GPL-3.0-only with source
included. They call the installed Frame Steam API; its proprietary library is
not redistributed in the SDK. Retail game assemblies, assets and saves are
never part of public runtime downloads.

## Until Then compatibility runtime

The experimental Godot 4.1.4 native-extension bundle retains Godot/GodotCpp
component notices and the MIT licenses for InkCPP, Threen, GodotSteam and the
public FMOD binding. Independently authored JSON/camera/color replacements use
the converter's GPL-3.0-only license, with nlohmann JSON 3.10.4 under MIT.
The bundle includes pinned source references, compatibility build recipes and
license texts. It contains no game content, proprietary FMOD libraries, Steam
runtime libraries or Steam SDK headers.

Personal Until Then conversions copy ARM64 audio libraries and the vendor
license from the owner's checksum-verified FMOD Studio API 2.02.35 Linux SDK.
FMOD's terms apply to those libraries; the framework license does not replace
them. Genuine Steam calls use the Frame's installed native Steam API. See
[the experimental profile](docs/backends/until-then.md).

## Train45 experimental native runtime

The optional Train45 runtime bundle contains the official Godot 4.5 ARM64
release export template (MIT and bundled third-party notices) and GodotSteam
GDExtension 4.19.1 for 4.4+ (MIT). Exact input, binary, license and archive
checksums are pinned in the runtime index and reproducible export recipe.
License/copyright texts and source references accompany converted packages.
See `experiments/train45/README.md` and its preserved license texts.
No Train45 content or Valve Steam API binary is redistributed in this bundle.
The launcher resolves Frame's installed native Steam API inside the converted
package; genuine API behavior is retained.

## Steam Artwork Companion

The standalone Frame companion is original project code under this repository's
AGPL-3.0 license. It uses Python and Tcl/Tk, and Pillow for image loading and previews.
Pillow uses its HPND license; upstream licensing is included with the collected
Pillow distribution metadata and documented at https://github.com/python-pillow/Pillow.
PyInstaller uses GPL with its bootloader exception. No Steam client library or
SteamGridDB artwork is bundled in the companion; images are supplied locally or
fetched by the user under the provider's terms.

## certifi CA bundle (Linux fallback)

Linux packages include certifi (`certifi/cacert.pem`), containing Mozilla's
maintained CA collection. certifi is distributed under the Mozilla Public
License 2.0: https://github.com/certifi/python-certifi/blob/master/LICENSE.
The bundle supplements unavailable system trust only; usable system roots and
explicit trust configuration take precedence. The Linux builder copies certifi's
distribution metadata and license; rebuild with maintained certifi releases.
