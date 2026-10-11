# Integrated STS2 two-stage conversion

The working-main GUI now includes the STS2 implementation imported from the
working `multi-engine-game-conversion-framework-by-tovakai-audit-sts2-remove-ownership-attestation`
checkout. It preserves the existing RenFrame, RPGMFrame, GodotSteam, GameMaker,
LÖVE, Construct and AGS routes. STS2 is detected before generic Godot handling.

Supported source releases are checked by the backend's pinned profiles. Unknown
releases are rejected with STS2 diagnostics rather than converted as generic Godot.
The GUI discovers FMOD Studio API 2.03.15 for Linux from a saved selection,
the configured environment, its dependency directory or Downloads. Discovery and
Convert both check the supported archive's size and SHA-256. Missing, removed or
corrupt SDK inputs open the existing download dialog before any conversion job.
SDK selection does not download vendor software or grant a vendor license.

Windows conversion creates a transfer ZIP containing prepared game data, selected
user-supplied SDK build inputs, installation scripts and software source. It is
not a finished native runtime package. Copy and extract it on Frame, install the
matching game through Steam and run `sh ./install.sh`. The installer validates
the Steam installation, downloads pinned build dependencies, builds native
components, verifies the result and reports Steam launch configuration. First
installation needs internet and the documented Frame build prerequisites.

The CLI accepts `build SOURCE --fmod-sdk ARCHIVE`. On Windows it defaults to the
same handoff workflow. Existing Frame build APIs and remote service support remain
available, but the GUI does not require SSH during Windows preparation.

The integrated backend software retains AGPL v3; see its local LICENSE and
THIRD_PARTY_NOTICES.md. No retail game files, FMOD SDK or dependency binaries are
committed to the repository or bundled in the converter application itself.

Integration validation includes the complete framework test suite, synthetic
handoff installation tests and frozen Windows conversion checks. These do not
establish new hardware gameplay results; prior STS2 hardware results belong to
the separate implementation session. Multiplayer, saves and further gameplay
must be assessed against the exact source release and generated package.
