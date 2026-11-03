"""Theme engine for Pillarium 2.0."""

from .freedesktop import (
    APPEARANCE_NAMESPACE,
    FreedesktopPreferences,
    detect_preferences,
    theme_from_preferences,
)
from .manager import ThemeManager
from .tokens import (
    BUILTIN_DARK,
    BUILTIN_LIGHT,
    BUILTIN_RETRO,
    BUILTIN_THEMES,
    COLOR_TOKENS,
    DEFAULT_METRICS,
    METRIC_TOKENS,
    Theme,
    contrasting_text,
    hex_to_rgb,
    relative_luminance,
    rgb_to_hex,
)

__all__ = [
    "APPEARANCE_NAMESPACE",
    "BUILTIN_DARK",
    "BUILTIN_LIGHT",
    "BUILTIN_RETRO",
    "BUILTIN_THEMES",
    "COLOR_TOKENS",
    "DEFAULT_METRICS",
    "METRIC_TOKENS",
    "FreedesktopPreferences",
    "Theme",
    "ThemeManager",
    "contrasting_text",
    "detect_preferences",
    "hex_to_rgb",
    "relative_luminance",
    "rgb_to_hex",
    "theme_from_preferences",
]
