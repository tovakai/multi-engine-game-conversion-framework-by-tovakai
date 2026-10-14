"""Legacy import alias for the MonoFrame Celeste profile implementation."""
import sys
from monoframe import celeste as _implementation
sys.modules[__name__] = _implementation
