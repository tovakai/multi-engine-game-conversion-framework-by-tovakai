"""Restore the legacy GodotSteam initialization contract for Godot 3.5 exports."""
from pathlib import Path
import re

LEGACY_INITIALIZER = r'''
Dictionary Steam::steamInitLegacy(bool retrieve_stats, uint32_t app_id, bool embed_callbacks) {
    Dictionary result;
    bool initialized = steamInit(app_id, embed_callbacks);
    int status = initialized ? k_EResultOK : k_EResultFail;
    String message = initialized ? "Steamworks active." : "Steamworks failed to initialize.";
    if (!isSteamRunning()) {
        status = k_EResultServiceUnavailable;
        message = "Steam not running.";
    } else if (SteamUser() == NULL) {
        status = k_EResultUnexpectedError;
        message = "Invalid app ID or app not installed.";
    }
    if (status == k_EResultOK && retrieve_stats && SteamUserStats() != NULL) {
        SteamUserStats()->RequestUserStats(SteamUser()->GetSteamID());
    }
    if (initialized && SteamUtils() != NULL) {
        current_app_id = SteamUtils()->GetAppID();
    }
    result["status"] = status;
    result["verbal"] = message;
    return result;
}
'''


def apply_legacy_initializer(module: Path) -> None:
    cpp,header = module/'godotsteam.cpp',module/'godotsteam.h'
    text, declarations = cpp.read_text(),header.read_text()
    if 'Steam::steamInitLegacy(' in text:
        return
    anchor = 'bool Steam::steamInit('
    if text.count(anchor) != 1:
        raise ValueError('Unexpected GodotSteam initialization implementation.')
    pattern = r'(?m)^([ \t]*)ClassDB::bind_method\(D_METHOD\("steamInit",[^\n]*&Steam::steamInit,[^\n]*$'
    binding = r'\1ClassDB::bind_method(D_METHOD("steamInit", "retrieve_stats", "app_id", "embed_callbacks"), &Steam::steamInitLegacy, DEFVAL(true), DEFVAL(0), DEFVAL(false));'
    text,count = re.subn(pattern,binding,text)
    if count != 1:
        raise ValueError('Unexpected GodotSteam steamInit binding.')
    text = text.replace(anchor,LEGACY_INITIALIZER+'\n'+anchor)
    declarations,count = re.subn(r'(?m)^([ \t]*)bool steamInit\(',
        r'\1Dictionary steamInitLegacy(bool retrieve_stats, uint32_t app_id, bool embed_callbacks);\n\1bool steamInit(',declarations)
    if count != 1:
        raise ValueError('Unexpected GodotSteam steamInit declaration.')
    cpp.write_text(text)
    header.write_text(declarations)
