/* Test-copy telemetry only. Observes RPG Maker input without changing it.
 * Enable with MEGCFBT_CONTROLLER_TEST_LOG=/absolute/path/events.jsonl.
 * Load after the engine scripts in the isolated test copy's index.html.
 */
(function () {
    "use strict";
    if (typeof require !== "function") return;
    var fs = require("fs");
    var output = process.env.MEGCFBT_CONTROLLER_TEST_LOG;
    if (!output) return;
    var failed = false;
    function record(kind, values) {
        if (failed) return;
        try {
            fs.appendFileSync(output, JSON.stringify({
                time: Date.now(), kind: kind, values: values
            }) + "\n");
        } catch (error) {
            failed = true;
            console.error("Controller test logging stopped:", error.message);
        }
    }
    record("start", {
        engine: typeof Utils !== "undefined" ? Utils.RPGMAKER_NAME : null,
        version: typeof Utils !== "undefined" ? Utils.RPGMAKER_VERSION : null,
        display: process.env.DISPLAY || null,
        wayland: process.env.WAYLAND_DISPLAY || null,
        steamAppId: process.env.SteamAppId || null
    });
    var controlKeys = /^(ArrowUp|ArrowDown|ArrowLeft|ArrowRight|Enter|Escape|Shift|Tab|PageUp|PageDown|[hHqQwW])$/;
    ["keydown", "keyup"].forEach(function (kind) {
        window.addEventListener(kind, function (event) {
            if (controlKeys.test(event.key)) record(kind, {key: event.key, repeat: event.repeat});
        }, true);
    });
    ["mousedown", "mouseup"].forEach(function (kind) {
        window.addEventListener(kind, function (event) {
            record(kind, {button: event.button, x: event.clientX, y: event.clientY});
        }, true);
    });
    ["focus", "blur"].forEach(function (kind) {
        window.addEventListener(kind, function () { record(kind, {}); });
    });
    var previous = "";
    setInterval(function () {
        if (failed || typeof Input === "undefined" || typeof TouchInput === "undefined") return;
        var state = {
            keys: Object.keys(Input._currentState || {}).filter(function (key) {
                return Input._currentState[key];
            }).sort(),
            direction: Input.dir4,
            mouse: {x: TouchInput.x, y: TouchInput.y, pressed: TouchInput.isPressed()},
            gamepads: Array.prototype.filter.call(navigator.getGamepads(), Boolean).map(function (pad) {
                return {
                    index: pad.index,
                    axes: Array.prototype.map.call(pad.axes, function (axis) { return Math.round(axis * 10) / 10; }),
                    buttons: Array.prototype.map.call(pad.buttons, function (button) { return Math.round(button.value * 10) / 10; })
                };
            })
        };
        var serialized = JSON.stringify(state);
        if (serialized !== previous) {
            previous = serialized;
            record("state", state);
        }
    }, 100);
}());
