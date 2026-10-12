/* Celeste's FMOD 1.10 studio ABI adapted to the owner's FMOD 2.03.15 SDK.
 * SPDX-License-Identifier: GPL-3.0-only
 * Calls the actual FMOD libraries; no offline or silent-audio stubs.
 * FMODStudioFix (Johnny on Flame, MIT) informed the version/parameter mapping.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <fmod_studio.h>

static void *real_symbol(const char *name) {
    static void *library;
    if (!library) library = dlopen("libfmodstudio.so.14", RTLD_NOW | RTLD_LOCAL);
    void *symbol = library ? dlsym(library, name) : NULL;
    if (!symbol) { fprintf(stderr, "Celeste FMOD compatibility: missing %s: %s\n", name, dlerror()); abort(); }
    return symbol;
}

FMOD_RESULT FMOD_Studio_System_Create(FMOD_STUDIO_SYSTEM **system, unsigned int version) {
    FMOD_RESULT (*function)(FMOD_STUDIO_SYSTEM **, unsigned int) = real_symbol("FMOD_Studio_System_Create");
    return function(system, FMOD_VERSION);
}

FMOD_RESULT Celeste_FMOD_System_Create(FMOD_SYSTEM **system) {
    FMOD_RESULT (*function)(FMOD_SYSTEM **, unsigned int) = real_symbol("FMOD_System_Create");
    return function(system, FMOD_VERSION);
}

FMOD_RESULT Celeste_FMOD_SetListenerAttributes(FMOD_STUDIO_SYSTEM *system, int listener, const FMOD_3D_ATTRIBUTES *attributes) {
    FMOD_RESULT (*function)(FMOD_STUDIO_SYSTEM *, int, const FMOD_3D_ATTRIBUTES *, const FMOD_VECTOR *) = real_symbol("FMOD_Studio_System_SetListenerAttributes");
    return function(system, listener, attributes, NULL);
}

FMOD_RESULT FMOD_Studio_System_GetLowLevelSystem(FMOD_STUDIO_SYSTEM *system, FMOD_SYSTEM **core) {
    FMOD_RESULT (*function)(FMOD_STUDIO_SYSTEM *, FMOD_SYSTEM **) = real_symbol("FMOD_Studio_System_GetCoreSystem");
    return function(system, core);
}

FMOD_RESULT FMOD_Studio_EventInstance_SetParameterValue(FMOD_STUDIO_EVENTINSTANCE *instance, const char *name, float value) {
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTINSTANCE *, const char *, float, FMOD_BOOL) = real_symbol("FMOD_Studio_EventInstance_SetParameterByName");
    return function(instance, name, value, 0);
}

FMOD_RESULT FMOD_Studio_EventInstance_GetParameterValue(FMOD_STUDIO_EVENTINSTANCE *instance, const char *name, float *value) {
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTINSTANCE *, const char *, float *, float *) = real_symbol("FMOD_Studio_EventInstance_GetParameterByName");
    return function(instance, name, value, NULL);
}

FMOD_RESULT FMOD_Studio_EventInstance_TriggerCue(FMOD_STUDIO_EVENTINSTANCE *instance) {
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTINSTANCE *) = real_symbol("FMOD_Studio_EventInstance_KeyOff");
    return function(instance);
}

/* Old structs have an integer index where FMOD 2 has a parameter ID. */
typedef struct { const char *name; int index; float minimum, maximum, defaultvalue; int type; } CelesteParameter;

static void copy_parameter(CelesteParameter *out, const FMOD_STUDIO_PARAMETER_DESCRIPTION *in, int index) {
    out->name = in->name; out->index = index; out->minimum = in->minimum;
    out->maximum = in->maximum; out->defaultvalue = in->defaultvalue; out->type = in->type;
}

FMOD_RESULT FMOD_Studio_EventDescription_GetParameter(FMOD_STUDIO_EVENTDESCRIPTION *event, const char *name, CelesteParameter *out) {
    FMOD_STUDIO_PARAMETER_DESCRIPTION value;
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTDESCRIPTION *, const char *, FMOD_STUDIO_PARAMETER_DESCRIPTION *) = real_symbol("FMOD_Studio_EventDescription_GetParameterDescriptionByName");
    FMOD_RESULT result = function(event, name, &value);
    if (result == FMOD_OK) copy_parameter(out, &value, 0);
    return result;
}

FMOD_RESULT FMOD_Studio_EventDescription_GetParameterByIndex(FMOD_STUDIO_EVENTDESCRIPTION *event, int index, CelesteParameter *out) {
    FMOD_STUDIO_PARAMETER_DESCRIPTION value;
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTDESCRIPTION *, int, FMOD_STUDIO_PARAMETER_DESCRIPTION *) = real_symbol("FMOD_Studio_EventDescription_GetParameterDescriptionByIndex");
    FMOD_RESULT result = function(event, index, &value);
    if (result == FMOD_OK) copy_parameter(out, &value, index);
    return result;
}

FMOD_RESULT FMOD_Studio_EventDescription_GetParameterCount(FMOD_STUDIO_EVENTDESCRIPTION *event, int *count) {
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTDESCRIPTION *, int *) = real_symbol("FMOD_Studio_EventDescription_GetParameterDescriptionCount");
    return function(event, count);
}

FMOD_RESULT FMOD_Studio_EventDescription_HasCue(FMOD_STUDIO_EVENTDESCRIPTION *event, FMOD_BOOL *value) {
    FMOD_RESULT (*function)(FMOD_STUDIO_EVENTDESCRIPTION *, FMOD_BOOL *) = real_symbol("FMOD_Studio_EventDescription_HasSustainPoint");
    return function(event, value);
}
