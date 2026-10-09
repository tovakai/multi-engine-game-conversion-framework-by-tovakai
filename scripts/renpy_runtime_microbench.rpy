# Install alongside diagnostics.rpy in a disposable converted package only.
# Opt-in synthetic cache/texture test; never reads or executes game labels.
init 1000 python:
    import os as _rf_bench_os
    if _rf_bench_os.environ.get("RENFRAME_MICROBENCH") == "1":
        def _rf_start_microbench():
            renpy.call_in_new_context("_renframe_microbench")
            renpy.quit()
        renpy.config.start_callbacks.append(_rf_start_microbench)

label _renframe_microbench:
    scene
    $ renpy.pause(0.1, hard=True)
    python:
        import json
        import time
        import renpy.display.im as im
        import gc
        import os
        clock = getattr(time, "perf_counter", time.time)
        # External JSON list chosen by the operator. Limit batch working set.
        with open(os.environ["RENFRAME_BENCH_ASSETS"], "r") as f:
            filenames = json.load(f)
        if not 1 <= len(filenames) <= 3:
            raise Exception("Microbenchmark requires 1-3 assets")
        images = [im.Image(filename) for filename in filenames]
        results = []
        for cycle in range(3):
            before = clock()
            renpy.free_memory()
            results.append(dict(cycle=cycle, phase="free_memory", duration_ms=(clock()-before)*1000))
            for phase in ("after_clear", "warm"):
                before = clock()
                for image in images:
                    im.cache.get(image, texture=True)
                results.append(dict(cycle=cycle, phase=phase, duration_ms=(clock()-before)*1000))
        with open(os.environ["RENFRAME_TRACE"] + ".microbench.json", "w") as f:
            json.dump(dict(synthetic=True, renderer=renpy.display.draw.__class__.__name__, results=results), f, indent=2)
    return
