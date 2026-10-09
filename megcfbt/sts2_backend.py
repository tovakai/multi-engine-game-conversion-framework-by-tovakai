"""Load the single standalone backend in-process, including frozen Windows apps."""

from pathlib import Path
import importlib
import sys
import threading

_lock = threading.RLock()


def module(name):
    from megcfbt.sts2 import tools_directory
    directory = tools_directory()
    with _lock:
        old = list(sys.path)
        try:
            sys.path.insert(0, str(directory))
            result = importlib.import_module(name)
            if Path(result.__file__).resolve().parent != directory.resolve():
                raise RuntimeError("Conflicting STS2 backend module: " + name)
            return result
        finally:
            sys.path[:] = old
