"""
presets.py — Save and load named plot-style presets as JSON files.

Presets are stored in  <project_root>/.presets/<name>.json
They capture all visual/style settings but nothing data-specific
(no file path, sheet, condition filter, label renames, or stat pair selection).
"""

from __future__ import annotations

import json
from pathlib import Path

# Presets live next to this file (the project root), not cwd.
PRESETS_DIR = Path(__file__).parent / ".presets"

# ---------------------------------------------------------------------------
# Default values for every saveable setting.
# Keys use the "ps_" prefix that matches the Streamlit widget key= arguments.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, object] = {
    # Plot type
    "ps_plot_type":        "bar+strip",
    # Y-axis
    "ps_log_scale":        False,
    "ps_show_grid":        False,
    "ps_error_bar":        "sd",
    "ps_cap_size":         0.08,
    # Data points
    "ps_show_points":      True,
    "ps_point_size":       4.0,
    "ps_point_alpha":      0.7,
    # Labels
    "ps_xlabel":           "Condition",
    "ps_leg_title":        "Treatment",
    "ps_show_legend":      True,
    "ps_legend_inside":    False,
    # Colors
    "ps_palette_name":     "iGEM",
    "ps_custom_colors":    [],
    "ps_bar_edge_width":   0.6,
    "ps_bar_edge_color":   "#000000",
    "ps_bar_alpha":        1.0,
    # Figure size
    "ps_bar_gap":          0.0,
    "ps_fig_width":        11,
    "ps_fig_height":       6,
    # Line plot
    "ps_x_numeric":        False,
    "ps_x_suffix":         "",
    "ps_x_tick_interval":  0.0,
    "ps_y_tick_interval":  0.0,
    "ps_error_style":      "band",
    "ps_line_width":       1.5,
    "ps_marker_style":     "o",
    "ps_marker_size":      6.0,
    "ps_trendline":        "none",
    "ps_trendline_source": "means",
    "ps_trendline_mode":   "overlay",
    # Tick marks
    "ps_tick_direction":    "out",
    "ps_major_tick_length": 4.0,
    "ps_major_tick_width":  0.8,
    "ps_minor_ticks_y":     0,
    "ps_minor_ticks_x":     0,
    "ps_minor_tick_length": 2.0,
    "ps_minor_tick_width":  0.6,
    # Statistics
    "ps_run_stats":        False,
    "ps_test_mode":        "ttest",
    "ps_compare_axis":     "conditions",
    "ps_show_ns":          False,
    "ps_show_pvalue":      False,
    "ps_show_significance": True,
    "ps_show_fold_change": False,
    "ps_bracket_linewidth": 0.9,
    "ps_bracket_fontsize": 11.0,
    # Typography
    "ps_font_family":      "sans-serif",
    "ps_font_mode":        "Global scale",
    "ps_font_scale":       1.0,
    "ps_fs_title":         14,
    "ps_fs_axis":          12,
    "ps_fs_tick":          10,
    "ps_fs_legend":        10,
    # Advanced
    "ps_y_format":         "auto",
    "ps_tick_rotation":    40,
    "ps_tick_fontsize_adv": 10,
    "ps_spines":           "open",
    "ps_spine_width":      1.0,
    "ps_ymin_str":         "",
    "ps_ymax_str":         "",
    "ps_xmin_str":         "",
    "ps_xmax_str":         "",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _ensure_default() -> None:
    """Create the Default preset from DEFAULTS if it doesn't exist yet."""
    PRESETS_DIR.mkdir(exist_ok=True)
    default_path = PRESETS_DIR / "Default.json"
    if not default_path.exists():
        default_path.write_text(
            json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8"
        )

_ensure_default()


_STARTUP_FILE = PRESETS_DIR / "_startup.txt"


def get_startup_preset() -> str:
    """Return the name of the preset loaded on session start (default: 'Default')."""
    if _STARTUP_FILE.exists():
        name = _STARTUP_FILE.read_text(encoding="utf-8").strip()
        if (PRESETS_DIR / f"{_sanitise(name)}.json").exists():
            return name
    return "Default"


def set_startup_preset(name: str) -> None:
    """Persist *name* as the startup preset."""
    PRESETS_DIR.mkdir(exist_ok=True)
    _STARTUP_FILE.write_text(name, encoding="utf-8")


def list_presets() -> list[str]:
    """Return sorted list of saved preset names."""
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def save(name: str, settings: dict) -> None:
    """Save *settings* (subset of DEFAULTS keys) as a named preset."""
    name = _sanitise(name)
    PRESETS_DIR.mkdir(exist_ok=True)
    data = {k: settings[k] for k in DEFAULTS if k in settings}
    (PRESETS_DIR / f"{name}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load(name: str) -> dict:
    """
    Load a preset and return a dict ready to merge into st.session_state.
    Missing keys are filled from DEFAULTS so the result is always complete.
    """
    path = PRESETS_DIR / f"{_sanitise(name)}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Fill any keys that were added after the preset was saved
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def delete(name: str) -> None:
    """Delete a preset file. No-op if it doesn't exist."""
    path = PRESETS_DIR / f"{_sanitise(name)}.json"
    if path.exists():
        path.unlink()


def exists(name: str) -> bool:
    return (PRESETS_DIR / f"{_sanitise(name)}.json").exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise(name: str) -> str:
    """Strip characters that are unsafe in filenames."""
    import re
    return re.sub(r'[\\/*?:"<>|]', "_", name.strip())
