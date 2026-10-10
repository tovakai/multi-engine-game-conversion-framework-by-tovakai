/* Keep native games on the selected Frame desktop after Steam initialization.
 * Steam on Frame can replace graphics environment variables during API init,
 * sending engines that initialize Steam before video to another X server.
 * This wrapper preserves graphics routing; all Steam calls use the real API.
 * SPDX-License-Identifier: GPL-3.0-only
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

static const char *graphics_keys[] = {
    "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY"
};
static _Thread_local unsigned init_depth;

struct snapshot {
    bool enabled;
    char *values[4];
};

static struct snapshot begin_init(void) {
    struct snapshot state = {0};
    const char *guard = getenv("TOVAKAI_FRAME_PRESERVE_GRAPHICS");
    ++init_depth;
    if (init_depth != 1 || !guard || strcmp(guard, "1") != 0)
        return state;
    state.enabled = true;
    for (unsigned i = 0; i < 4; ++i) {
        const char *value = getenv(graphics_keys[i]);
        if (value) {
            state.values[i] = strdup(value);
            if (!state.values[i]) {
                state.enabled = false;
                break;
            }
        }
    }
    return state;
}

static void finish_init(struct snapshot *state) {
    for (unsigned i = 0; i < 4; ++i) {
        if (state->enabled) {
            if (state->values[i])
                setenv(graphics_keys[i], state->values[i], 1);
            else
                unsetenv(graphics_keys[i]);
        }
        free(state->values[i]);
    }
    --init_depth;
}

bool SteamAPI_Init(void) {
    bool (*real_init)(void) = dlsym(RTLD_NEXT, "SteamAPI_Init");
    struct snapshot state = begin_init();
    bool result = real_init ? real_init() : false;
    finish_init(&state);
    return result;
}

int SteamAPI_InitFlat(char *error_message) {
    int (*real_init)(char *) = dlsym(RTLD_NEXT, "SteamAPI_InitFlat");
    struct snapshot state = begin_init();
    int result = real_init ? real_init(error_message) : 1;
    finish_init(&state);
    return result;
}

int SteamInternal_SteamAPI_Init(const char *interfaces, char *error_message) {
    int (*real_init)(const char *, char *) = dlsym(RTLD_NEXT, "SteamInternal_SteamAPI_Init");
    struct snapshot state = begin_init();
    int result = real_init ? real_init(interfaces, error_message) : 1;
    finish_init(&state);
    return result;
}
