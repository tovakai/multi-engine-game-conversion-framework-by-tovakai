/* Use the supported real Steam initialization API while preserving Frame video.
 * SPDX-License-Identifier: GPL-3.0-only */
#define _GNU_SOURCE
#include <stdbool.h>
#include <dlfcn.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
bool Celeste_SteamAPI_Init(void) {
    const char *keys[] = {"DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY"};
    char *values[4] = {0};
    for (int i = 0; i < 4; ++i) {
        const char *value = getenv(keys[i]);
        if (value) values[i] = strdup(value);
    }
    void *library = dlopen("libsteam_api.so", RTLD_NOW | RTLD_LOCAL);
    bool (*initialize)(void) = library ? dlsym(library, "SteamAPI_InitSafe") : NULL;
    bool result = initialize && initialize();
    for (int i = 0; i < 4; ++i) {
        if (values[i]) setenv(keys[i], values[i], 1); else unsetenv(keys[i]);
        free(values[i]);
    }
    fprintf(stderr, "Celeste: real SteamAPI_InitSafe = %s\n", result ? "true" : "false");
    return result;
}
