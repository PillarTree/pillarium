"""Pillarium – a lightweight X11 window manager / desktop environment.

The project may live under any directory name; all data-file locations
are resolved by :mod:`pillarium.paths` and can be overridden with
environment variables (see that module for details).
"""

try:
    from PIL import Image as _PILImage

    if not hasattr(_PILImage.Image, "tostring"):
        # Pillow >= 10 removed Image.tostring(); legacy Xlib builds still
        # call it in put_pil_image, so restore it for compatibility.
        _PILImage.Image.tostring = _PILImage.Image.tobytes
except Exception:
    pass

from .wm import Pillarium

__version__ = "1.0.6"
__all__ = ["Pillarium"]
