"""Compatibility entry point for the shared guided FMOD SDK dialog."""
from megcfbt.fmod_sdk_setup import FmodSdkDialog

class Sts2SdkDialog(FmodSdkDialog):
    def __init__(self, app):
        super().__init__(app, 'sts2')
