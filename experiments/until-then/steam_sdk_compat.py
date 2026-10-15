"""Restore native C++ helpers omitted from Proton's generated SDK headers.

These delegate to the existing Steam SDK interfaces. They do not replace
Steam services with stubs. Semantics follow Valve's GameNetworkingSockets
public networking headers (BSD-3-Clause).
"""
from pathlib import Path


def normalize_proton_headers(base: Path) -> None:
    """Normalize the pinned Proton 1.62 header snapshot for native C++."""
    replacements = [
        ('isteamremoteplay.h','} data;','};',1),
        ('isteaminput.h','} x;','};',1),
        ('steamnetworkingtypes.h','} data;','};',2),
        ('steamnetworkingtypes.h','#if 0\ninline void SteamNetworkingIPAddr::Clear()',
         '#if 1\ninline void SteamNetworkingIPAddr::Clear()',1),
    ]
    for filename,old,new,expected in replacements:
        path = base/filename
        text = path.read_text()
        if text.count(old) != expected:
            raise ValueError(f'Unexpected SDK header layout: {filename}')
        path.write_text(text.replace(old,new))
    header = base/'steam_api.h'
    header.write_text(header.read_text()+'\n'+NETWORKING_INLINE_HELPERS)

NETWORKING_INLINE_HELPERS = r'''
#ifndef TOVAKAI_STEAM_NETWORKING_INLINE_HELPERS
#define TOVAKAI_STEAM_NETWORKING_INLINE_HELPERS
inline void ISteamNetworkingUtils::InitRelayNetworkAccess() {
    CheckPingDataUpToDate(1e10f);
}
inline bool ISteamNetworkingUtils::SetGlobalConfigValueInt32(ESteamNetworkingConfigValue key, int32 value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Global, 0, k_ESteamNetworkingConfig_Int32, &value);
}
inline bool ISteamNetworkingUtils::SetGlobalConfigValueFloat(ESteamNetworkingConfigValue key, float value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Global, 0, k_ESteamNetworkingConfig_Float, &value);
}
inline bool ISteamNetworkingUtils::SetGlobalConfigValueString(ESteamNetworkingConfigValue key, const char *value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Global, 0, k_ESteamNetworkingConfig_String, value);
}
inline bool ISteamNetworkingUtils::SetGlobalConfigValuePtr(ESteamNetworkingConfigValue key, void *value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Global, 0, k_ESteamNetworkingConfig_Ptr, &value);
}
inline bool ISteamNetworkingUtils::SetConnectionConfigValueInt32(HSteamNetConnection connection, ESteamNetworkingConfigValue key, int32 value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Connection, connection, k_ESteamNetworkingConfig_Int32, &value);
}
inline bool ISteamNetworkingUtils::SetConnectionConfigValueFloat(HSteamNetConnection connection, ESteamNetworkingConfigValue key, float value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Connection, connection, k_ESteamNetworkingConfig_Float, &value);
}
inline bool ISteamNetworkingUtils::SetConnectionConfigValueString(HSteamNetConnection connection, ESteamNetworkingConfigValue key, const char *value) {
    return SetConfigValue(key, k_ESteamNetworkingConfig_Connection, connection, k_ESteamNetworkingConfig_String, value);
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_SteamNetConnectionStatusChanged(void (*callback)(SteamNetConnectionStatusChangedCallback_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_ConnectionStatusChanged, reinterpret_cast<void *>(callback));
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_SteamNetAuthenticationStatusChanged(void (*callback)(SteamNetAuthenticationStatus_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_AuthStatusChanged, reinterpret_cast<void *>(callback));
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_SteamRelayNetworkStatusChanged(void (*callback)(SteamRelayNetworkStatus_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_RelayNetworkStatusChanged, reinterpret_cast<void *>(callback));
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_FakeIPResult(void (*callback)(SteamNetworkingFakeIPResult_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_FakeIPResult, reinterpret_cast<void *>(callback));
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_MessagesSessionRequest(void (*callback)(SteamNetworkingMessagesSessionRequest_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_MessagesSessionRequest, reinterpret_cast<void *>(callback));
}
inline bool ISteamNetworkingUtils::SetGlobalCallback_MessagesSessionFailed(void (*callback)(SteamNetworkingMessagesSessionFailed_t *)) {
    return SetGlobalConfigValuePtr(k_ESteamNetworkingConfig_Callback_MessagesSessionFailed, reinterpret_cast<void *>(callback));
}
inline void SteamNetworkingIPAddr::ToString(char *buffer, size_t length, bool with_port) const {
    SteamNetworkingUtils()->SteamNetworkingIPAddr_ToString(*this, buffer, length, with_port);
}
inline bool SteamNetworkingIPAddr::ParseString(const char *text) {
    return SteamNetworkingUtils()->SteamNetworkingIPAddr_ParseString(this, text);
}
inline ESteamNetworkingFakeIPType SteamNetworkingIPAddr::GetFakeIPType() const {
    return SteamNetworkingUtils()->SteamNetworkingIPAddr_GetFakeIPType(*this);
}
inline void SteamNetworkingIdentity::ToString(char *buffer, size_t length) const {
    SteamNetworkingUtils()->SteamNetworkingIdentity_ToString(*this, buffer, length);
}
inline bool SteamNetworkingIdentity::ParseString(const char *text) {
    return SteamNetworkingUtils()->SteamNetworkingIdentity_ParseString(this, text);
}
#endif
'''
