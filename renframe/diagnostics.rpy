# Optional generic Ren'Py 7/8 runtime diagnostics. Install ONLY in a converted copy.
# No behavior changes unless RENFRAME_DIAGNOSTICS=1 or tuning variables are set.
init 999 python:
    import os as _rf_os

    def _rf_install():
        import atexit
        import collections
        import functools
        import json
        import threading
        import time
        import gc
        import renpy.loader
        import renpy.display.im
        import renpy.display.core
        import renpy.display.screen

        enabled = _rf_os.environ.get("RENFRAME_DIAGNOSTICS") == "1"
        # Explicit experimental overrides; absent variables preserve game settings.
        for env, setting, low, high in (
            ("RENFRAME_CACHE_MB", "image_cache_size_mb", 32, 512),
            ("RENFRAME_PREDICT_STATEMENTS", "predict_statements", 0, 128),
        ):
            value = _rf_os.environ.get(env)
            if value is not None:
                value = int(value)
                if not low <= value <= high:
                    raise Exception("%s must be between %d and %d" % (env, low, high))
                setattr(renpy.config, setting, value)
                if setting == "image_cache_size_mb":
                    renpy.config.image_cache_size = None
        if not enabled:
            return

        path = _rf_os.environ.get("RENFRAME_TRACE")
        if not path or not _rf_os.path.isabs(path):
            raise Exception("Set RENFRAME_TRACE to an absolute JSONL output path")
        clock = getattr(time, "perf_counter", time.time)
        lock = threading.RLock()
        totals = {}
        events = collections.deque(maxlen=4096)
        dropped = [0]
        started = clock()
        last_flush = [started]
        output = open(path, "w")

        def emit(value):
            output.write(json.dumps(value, sort_keys=True) + "\n")

        emit(dict(type="configuration", wall_time=time.time(),
                  version=renpy.version, resolution=[renpy.config.screen_width, renpy.config.screen_height],
                  cache_mb=renpy.config.image_cache_size_mb,
                  cache_screens=renpy.config.image_cache_size,
                  predict_statements=renpy.config.predict_statements,
                  predict_screens=renpy.config.predict_screens,
                  less_memory=renpy.game.less_memory,
                  environment=dict((k, v) for k, v in _rf_os.environ.items()
                                   if k.startswith(("RENPY_", "RENFRAME_", "SDL_")))))
        output.flush()

        def record(name, elapsed, extra=None):
            with lock:
                row = totals.setdefault(name, [0, 0.0, 0.0])
                row[0] += 1
                row[1] += elapsed
                row[2] = max(row[2], elapsed)
                if elapsed >= 0.005:
                    if len(events) == events.maxlen:
                        dropped[0] += 1
                    event = dict(type="slow_call", operation=name,
                                 end_s=clock() - started, duration_ms=elapsed * 1000,
                                 thread=threading.current_thread().name)
                    if extra:
                        event.update(extra)
                    events.append(event)

        def wrap(owner, attribute, category):
            original = getattr(owner, attribute, None)
            if original is None:
                emit(dict(type="unavailable_hook", operation=category))
                return
            @functools.wraps(original)
            def measured(*args, **kwargs):
                before = clock()
                try:
                    return original(*args, **kwargs)
                finally:
                    record(category, clock() - before)
            try:
                setattr(owner, attribute, measured)
                emit(dict(type="installed_hook", operation=category))
            except (TypeError, AttributeError):
                emit(dict(type="unavailable_hook", operation=category))

        im = renpy.display.im
        original_get = im.Cache.get
        @functools.wraps(original_get)
        def cache_get(self, image, *args, **kwargs):
            predict = kwargs.get("predict", args[0] if args else False)
            entry = self.cache.get(image)
            kind = "absent" if entry is None else ("texture" if entry.texture is not None else "surface")
            before = clock()
            try:
                return original_get(self, image, *args, **kwargs)
            finally:
                record("cache.%s.%s" % ("predict" if predict else "demand", kind), clock() - before)
        im.Cache.get = cache_get
        for owner, attribute, category in (
            (renpy.loader, "load", "loader.open"),
            (renpy.loader, "loadable", "loader.lookup"),
            (renpy.loader, "transfn", "loader.filesystem_lookup"),
            (renpy.loader.SubFile, "read", "archive.read"),
            (im.Image, "load", "image.load_inclusive"),
            (im.Cache, "preload_texture", "prediction.preload_inclusive"),
            (im.Cache, "cleanout", "cache.evict"),
            (im.Cache, "clear", "cache.clear"),
            (gc, "collect", "memory.gc"),
            (renpy.exports, "free_memory", "memory.free_inclusive"),
            (renpy.display.core.Interface, "kill_textures", "memory.kill_textures"),
            (renpy.display.core.Interface, "kill_surfaces", "memory.kill_surfaces"),
            (renpy.display.core.Interface, "draw_screen", "renderer.draw_inclusive"),
            (renpy.display.screen.ScreenDisplayable, "update", "screen.evaluate_inclusive"),
        ):
            wrap(owner, attribute, category)
        # renpy.free_memory is a re-export, so instrument its public alias too.
        renpy.free_memory = renpy.exports.free_memory

        input_serial = [0]
        last_input = [None]
        drawn_serial = [0]
        def queue_event(event):
            with lock:
                if len(events) == events.maxlen:
                    dropped[0] += 1
                events.append(event)
        pygame = renpy.display.core.pygame
        input_types = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.KEYDOWN)
        def observe_input(attribute):
            original = getattr(renpy.display.core.Interface, attribute, None)
            if original is None:
                return
            @functools.wraps(original)
            def observed(*args, **kwargs):
                event = original(*args, **kwargs)
                if event is not None and getattr(event, "type", None) in input_types:
                    input_serial[0] += 1
                    last_input[0] = clock()
                    queue_event(dict(type="input", serial=input_serial[0],
                                     event_type=event.type, elapsed_s=last_input[0]-started))
                return event
            setattr(renpy.display.core.Interface, attribute, observed)
        observe_input("event_poll")
        observe_input("event_wait")
        original_draw = renpy.display.core.Interface.draw_screen
        @functools.wraps(original_draw)
        def observed_draw(*args, **kwargs):
            result = original_draw(*args, **kwargs)
            if last_input[0] is not None and input_serial[0] != drawn_serial[0]:
                queue_event(dict(type="first_draw_after_input", serial=input_serial[0],
                                 elapsed_s=clock()-started,
                                 duration_ms=(clock()-last_input[0])*1000))
                drawn_serial[0] = input_serial[0]
            return result
        renpy.display.core.Interface.draw_screen = observed_draw

        renderer_hooked = [False]
        def flush(final=False):
            now = clock()
            if not final and now - last_flush[0] < 2:
                return
            if not renderer_hooked[0] and renpy.display.draw is not None:
                wrap(renpy.display.draw, "load_texture", "renderer.texture_inclusive")
                renderer_hooked[0] = True
                emit(dict(type="renderer", information=renpy.display.draw.__class__.__name__))
            with lock:
                while events:
                    emit(events.popleft())
                emit(dict(type="aggregate", elapsed_s=now-started, cumulative=True,
                          operations=dict((k, dict(calls=v[0], total_ms=v[1]*1000, max_ms=v[2]*1000))
                                          for k, v in totals.items()),
                          dropped_events=dropped[0]))
            output.flush()
            last_flush[0] = now

        renpy.config.interact_callbacks.append(flush)
        atexit.register(lambda: flush(True))
        # Explicit separate high-overhead Python profiling run, main thread only.
        if _rf_os.environ.get("RENFRAME_CPROFILE") == "1":
            import cProfile
            profiler = cProfile.Profile()
            profiler.enable()
            def save_profile():
                profiler.disable()
                profiler.dump_stats(path + ".pstats")
            atexit.register(save_profile)

    _rf_install()
