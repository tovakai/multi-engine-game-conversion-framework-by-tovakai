# Train45 runtime preparation

Use the exact official Godot 4.5 stable export templates and GodotSteam 4.19.1
GDExtension for 4.4+ (not the editor or a built-in module runtime):

- https://github.com/godotengine/godot-builds/releases/download/4.5-stable/Godot_v4.5-stable_export_templates.tpz
- https://codeberg.org/godotsteam/godotsteam/releases/download/v4.19.1-gde/godotsteam-4.19.1-gdextension-plugin-4.4.zip

`export_runtime.py --templates <tpz> --godotsteam <zip> --output build/runtime-bundles/godot-4.5-train45-native-arm64-v1.tar.gz`

The script verifies both complete input archives, all binary/license hashes and
the deterministic final archive against the shipped index. Application builders
verify and embed this optional build input. No game files or Valve binaries are
included. License/copyright texts are retained verbatim from pinned Godot 4.5
sources and the official GodotSteam archive. Public provisioning is pending;
no application release/tag is created by this recipe.
