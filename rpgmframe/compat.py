"""Generic Windows-to-Linux compatibility helpers for MV/MZ builds."""

from __future__ import annotations

import os
import re
from pathlib import Path

from rpgmframe.models import EngineVariant


_COMPAT_SCRIPT_NAME = "rpgmframe-compat.js"
_COMPAT_SCRIPT_REF = f"js/{_COMPAT_SCRIPT_NAME}"

_COMPAT_JS = r'''// RPGMFrame generic Windows-to-Linux compatibility shim.
(function() {
    "use strict";

    if (typeof require !== "function" || typeof process === "undefined") {
        return;
    }

    var fs = require("fs");
    var path = require("path");
    var packageRoot = path.dirname(process.execPath);
    var originalExistsSync = fs.existsSync.bind(fs);
    var originalReaddirSync = fs.readdirSync.bind(fs);
    var resolutionCache = Object.create(null);

    function isMissingError(error) {
        return error && (error.code === "ENOENT" || error.code === "ENOTDIR");
    }

    function isInsidePackage(candidate) {
        var relative = path.relative(packageRoot, candidate);
        return relative === "" || (
            relative !== ".." &&
            relative.indexOf(".." + path.sep) !== 0 &&
            !path.isAbsolute(relative)
        );
    }

    function resolveCaseInsensitive(input) {
        if (typeof input !== "string") {
            return input;
        }

        var absolute = path.resolve(input);
        if (!isInsidePackage(absolute)) {
            return input;
        }
        if (originalExistsSync(absolute)) {
            return input;
        }
        if (Object.prototype.hasOwnProperty.call(resolutionCache, absolute)) {
            return resolutionCache[absolute];
        }

        var parsed = path.parse(absolute);
        var current = parsed.root;
        var tail = absolute.slice(parsed.root.length);
        var segments = tail.split(path.sep).filter(function(segment) {
            return segment.length > 0;
        });

        for (var i = 0; i < segments.length; i++) {
            var segment = segments[i];
            var direct = path.join(current, segment);
            if (originalExistsSync(direct)) {
                current = direct;
                continue;
            }

            var entries;
            try {
                entries = originalReaddirSync(current);
            } catch (error) {
                return input;
            }

            var folded = segment.toLocaleLowerCase();
            var matches = entries.filter(function(entry) {
                return entry.toLocaleLowerCase() === folded;
            });

            // Never guess if the source tree contains a case-insensitive
            // collision such as Foo.png and foo.png.
            if (matches.length !== 1) {
                return input;
            }
            current = path.join(current, matches[0]);
        }

        if (!originalExistsSync(current)) {
            return input;
        }

        resolutionCache[absolute] = current;
        return current;
    }

    function patchSync(name) {
        var original = fs[name];
        if (typeof original !== "function") {
            return;
        }

        fs[name] = function() {
            var args = Array.prototype.slice.call(arguments);
            try {
                return original.apply(fs, args);
            } catch (error) {
                if (!isMissingError(error)) {
                    throw error;
                }
                var resolved = resolveCaseInsensitive(args[0]);
                if (resolved === args[0]) {
                    throw error;
                }
                args[0] = resolved;
                return original.apply(fs, args);
            }
        };
    }

    function patchAsync(name) {
        var original = fs[name];
        if (typeof original !== "function") {
            return;
        }

        fs[name] = function() {
            var args = Array.prototype.slice.call(arguments);
            var originalPath = args[0];
            var callbackIndex = args.length - 1;
            var callback = args[callbackIndex];

            if (typeof callback !== "function") {
                return original.apply(fs, args);
            }

            args[callbackIndex] = function() {
                var callbackArgs = Array.prototype.slice.call(arguments);
                var error = callbackArgs[0];
                if (isMissingError(error)) {
                    var resolved = resolveCaseInsensitive(originalPath);
                    if (resolved !== originalPath) {
                        var retryArgs = args.slice();
                        retryArgs[0] = resolved;
                        retryArgs[callbackIndex] = callback;
                        return original.apply(fs, retryArgs);
                    }
                }
                return callback.apply(null, callbackArgs);
            };

            return original.apply(fs, args);
        };
    }

    var originalExists = fs.existsSync.bind(fs);
    fs.existsSync = function(candidate) {
        if (originalExists(candidate)) {
            return true;
        }
        var resolved = resolveCaseInsensitive(candidate);
        return resolved !== candidate && originalExists(resolved);
    };

    [
        "readFileSync",
        "statSync",
        "lstatSync",
        "readdirSync",
        "accessSync",
        "openSync"
    ].forEach(patchSync);

    [
        "readFile",
        "stat",
        "lstat",
        "readdir",
        "access",
        "open"
    ].forEach(patchAsync);

    if (fs.promises) {
        [
            "readFile",
            "stat",
            "lstat",
            "readdir",
            "access",
            "open"
        ].forEach(function(name) {
            var original = fs.promises[name];
            if (typeof original !== "function") {
                return;
            }
            fs.promises[name] = async function() {
                var args = Array.prototype.slice.call(arguments);
                try {
                    return await original.apply(fs.promises, args);
                } catch (error) {
                    if (!isMissingError(error)) {
                        throw error;
                    }
                    var resolved = resolveCaseInsensitive(args[0]);
                    if (resolved === args[0]) {
                        throw error;
                    }
                    args[0] = resolved;
                    return await original.apply(fs.promises, args);
                }
            };
        });
    }

    function rewriteResourceUrl(value) {
        if (typeof value !== "string" || typeof document === "undefined") {
            return value;
        }

        var parsed;
        try {
            parsed = new URL(value, document.baseURI);
        } catch (error) {
            return value;
        }

        if (
            parsed.protocol !== window.location.protocol ||
            parsed.host !== window.location.host
        ) {
            return value;
        }

        var relativeUrlPath;
        try {
            relativeUrlPath = decodeURIComponent(parsed.pathname).replace(/^\/+/, "");
        } catch (error) {
            return value;
        }

        var candidate = path.join(packageRoot, relativeUrlPath);
        var resolved = resolveCaseInsensitive(candidate);
        if (resolved === candidate || !originalExistsSync(resolved)) {
            return value;
        }

        var actualRelative = path.relative(packageRoot, resolved)
            .split(path.sep)
            .map(encodeURIComponent)
            .join("/");
        parsed.pathname = "/" + actualRelative;
        return parsed.href;
    }

    if (typeof XMLHttpRequest !== "undefined") {
        var originalOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function() {
            var args = Array.prototype.slice.call(arguments);
            if (args.length > 1) {
                args[1] = rewriteResourceUrl(args[1]);
            }
            return originalOpen.apply(this, args);
        };
    }

    if (typeof window !== "undefined" && typeof window.fetch === "function") {
        var originalFetch = window.fetch.bind(window);
        window.fetch = function(input, init) {
            if (typeof input === "string") {
                input = rewriteResourceUrl(input);
            }
            return originalFetch(input, init);
        };
    }

    function patchSrcProperty(proto) {
        if (!proto) {
            return;
        }
        var descriptor = Object.getOwnPropertyDescriptor(proto, "src");
        if (!descriptor || typeof descriptor.set !== "function") {
            return;
        }
        try {
            Object.defineProperty(proto, "src", {
                configurable: descriptor.configurable,
                enumerable: descriptor.enumerable,
                get: descriptor.get,
                set: function(value) {
                    return descriptor.set.call(this, rewriteResourceUrl(value));
                }
            });
        } catch (error) {
            // Some runtimes expose non-configurable DOM descriptors.
        }
    }

    if (typeof HTMLImageElement !== "undefined") {
        patchSrcProperty(HTMLImageElement.prototype);
    }
    if (typeof HTMLAudioElement !== "undefined") {
        patchSrcProperty(HTMLAudioElement.prototype);
    }
    if (typeof HTMLVideoElement !== "undefined") {
        patchSrcProperty(HTMLVideoElement.prototype);
    }
})();
'''


def _inject_script(index_html: Path, script_ref: str) -> bool:
    try:
        html = index_html.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False

    if script_ref.lower() in html.lower():
        return False

    tag = f'<script type="text/javascript" src="{script_ref}"></script>\n'
    first_script = re.search(r"<script\b", html, flags=re.IGNORECASE)
    if first_script:
        html = html[: first_script.start()] + tag + html[first_script.start() :]
    else:
        closing_head = re.search(r"</head\s*>", html, flags=re.IGNORECASE)
        if closing_head:
            html = html[: closing_head.start()] + tag + html[closing_head.start() :]
        else:
            html = tag + html

    index_html.write_text(html, encoding="utf-8", newline="\n")
    return True


def _repair_mv_negative_skipcount(payload_root: Path) -> bool:
    """
    Apply the upstream RPG Maker MV render-freeze fix when the old core is present.

    Older MV cores only render when Graphics._skipCount is exactly zero. If a
    clock adjustment makes the calculated skip count negative, the renderer can
    remain skipped indefinitely while game logic/audio continue. The upstream
    CoreScript fix changes the comparison to <= 0.
    """
    core = payload_root / "js" / "rpg_core.js"
    if not core.is_file():
        return False

    try:
        core_text = core.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False

    old = "if (this._skipCount === 0) {"
    new = "if (this._skipCount <= 0) {"

    # Stay conservative: patch only the exact known old CoreScript expression,
    # and only when it appears once.
    if core_text.count(old) != 1:
        return False

    core.write_text(
        core_text.replace(old, new, 1),
        encoding="utf-8",
        newline="\n",
    )
    return True


def _repair_mv_fpsmeter(payload_root: Path) -> bool:
    core = payload_root / "js" / "rpg_core.js"
    index_html = payload_root / "index.html"
    libs = payload_root / "js" / "libs"
    if not core.is_file() or not index_html.is_file() or not libs.is_dir():
        return False

    try:
        core_text = core.read_text(encoding="utf-8-sig", errors="ignore")
        html = index_html.read_text(encoding="utf-8-sig")
        entries = list(libs.iterdir())
    except OSError:
        return False

    if "FPSMeter" not in core_text or re.search(r"fpsmeter\.js", html, re.IGNORECASE):
        return False

    fpsmeter = next(
        (
            entry
            for entry in entries
            if entry.is_file() and entry.name.casefold() == "fpsmeter.js"
        ),
        None,
    )
    if fpsmeter is None:
        return False

    core_script = re.search(
        r"""<script\b[^>]*\bsrc=["'][^"']*rpg_core\.js[^"']*["'][^>]*>""",
        html,
        flags=re.IGNORECASE,
    )
    if core_script is None:
        return False

    tag = (
        '<script type="text/javascript" '
        f'src="js/libs/{fpsmeter.name}"></script>\n'
    )
    html = html[: core_script.start()] + tag + html[core_script.start() :]
    index_html.write_text(html, encoding="utf-8", newline="\n")
    return True


def _case_collisions(root: Path) -> list[str]:
    collisions: list[str] = []
    for directory, dirnames, filenames in os.walk(root):
        names = dirnames + filenames
        groups: dict[str, list[str]] = {}
        for name in names:
            groups.setdefault(name.casefold(), []).append(name)

        base = Path(directory)
        for matches in groups.values():
            if len(matches) < 2:
                continue
            relative = base.relative_to(root)
            prefix = "" if relative == Path(".") else f"{relative.as_posix()}/"
            collisions.append(prefix + " | ".join(sorted(matches)))
    return collisions


def install_compatibility(
    payload_root: Path,
    *,
    engine: EngineVariant,
) -> list[str]:
    """Install conservative compatibility repairs into a copied MV/MZ payload."""
    warnings: list[str] = []

    js_dir = payload_root / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    (js_dir / _COMPAT_SCRIPT_NAME).write_text(
        _COMPAT_JS,
        encoding="utf-8",
        newline="\n",
    )

    index_html = payload_root / "index.html"
    if _inject_script(index_html, _COMPAT_SCRIPT_REF):
        warnings.append(
            "Installed generic Linux compatibility shim for case-insensitive "
            "game asset and Node fs reads"
        )

    if engine is EngineVariant.MV and _repair_mv_negative_skipcount(payload_root):
        warnings.append(
            "Applied upstream RPG Maker MV render-freeze fix for negative "
            "Graphics._skipCount"
        )

    if engine is EngineVariant.MV and _repair_mv_fpsmeter(payload_root):
        warnings.append(
            "Repaired missing fpsmeter.js script include required by RPG Maker MV core"
        )

    collisions = _case_collisions(payload_root)
    if collisions:
        preview = "; ".join(collisions[:5])
        if len(collisions) > 5:
            preview += f"; +{len(collisions) - 5} more"
        warnings.append(
            "Case-insensitive path collisions detected; ambiguous mismatched "
            f"requests will not be rewritten: {preview}"
        )

    return warnings
