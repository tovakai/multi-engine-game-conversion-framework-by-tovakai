/* Flat-API compatibility for older managed Steamworks wrappers.
 * All requests go to the real Frame Steam client library. No offline stubs.
 * SPDX-License-Identifier: GPL-3.0-only
 */
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <dlfcn.h>

static void *real_library(void) {
    static void *library;
    if (!library) library = dlopen("libsteam_api.so", RTLD_NOW | RTLD_LOCAL);
    return library;
}

static void *real_symbol(const char *name) {
    void *library = real_library();
    return library ? dlsym(library, name) : 0;
}

void *SteamAPI_SteamUser_v021(void) {
    void *(*factory)(void) = real_symbol("SteamAPI_SteamUser_v023");
    return factory ? factory() : 0;
}

void *SteamAPI_SteamUserStats_v012(void) {
    void *(*factory)(void) = real_symbol("SteamAPI_SteamUserStats_v013");
    return factory ? factory() : 0;
}

bool SteamAPI_ISteamUserStats_RequestCurrentStats(void *stats) {
    void *(*user_factory)(void) = real_symbol("SteamAPI_SteamUser_v023");
    uint64_t (*user_id)(void *) = real_symbol("SteamAPI_ISteamUser_GetSteamID");
    uint64_t (*request)(void *, uint64_t) = real_symbol("SteamAPI_ISteamUserStats_RequestUserStats");
    if (!stats || !user_factory || !user_id || !request) return false;
    void *user = user_factory();
    return user && request(stats, user_id(user)) != 0;
}

/* Linker dependencies supply unmodified API symbols and the shared graphics
 * init guard; export lookups from the managed wrapper search those libraries. */
void monoframe_steam_bridge(void) {}
