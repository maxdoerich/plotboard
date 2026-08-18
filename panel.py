"""
panel.py — Multi-panel matplotlib figures composed from independent plot configs.

A "panel" is a dict with the keys:
    mode    : "plot" | "empty"
    df      : tidy DataFrame (only used when mode="plot")
    config  : kwargs forwarded verbatim to plotter.draw_plot
    ylim    : optional (min, max) — applied after tight_layout
    xlim    : optional (min, max) — applied after tight_layout
    label   : optional custom label string (overrides label_style)

Use `make_panel_figure(panels, rows=, cols=, ...)` to build a single
matplotlib Figure with one axes per slot, automatic panel labels (A/B/C,
1/2/3, I/II/III, …), and rows*cols subplots.
"""

from __future__ import annotations

import warnings

import matplotlib
from matplotlib.figure import Figure

from plotter import _apply_axis_limits, draw_plot, plot_style

# ---------------------------------------------------------------------------
# Defaults consumed by the Streamlit UI (kept here so panel.py owns its keys)
# ---------------------------------------------------------------------------
PANEL_DEFAULTS: dict[str, object] = {
    "ph_rows":             2,
    "ph_cols":             2,
    "ph_fig_width":        12,
    "ph_fig_height":       9,
    "ph_wspace":           0.30,
    "ph_hspace":           0.40,
    "ph_label_style":      "A",
    "ph_label_fontsize":   16,
    "ph_label_fontweight": "bold",
    "ph_label_x_offset":   -0.12,
    "ph_label_y_offset":   1.03,
}

LABEL_STYLES: list[str] = ["A", "a", "1", "I", "i", "(A)", "none"]
LABEL_STYLE_DISPLAY: dict[str, str] = {
    "A":    "A B C …",
    "a":    "a b c …",
    "1":    "1 2 3 …",
    "I":    "I II III …",
    "i":    "i ii iii …",
    "(A)":  "(A) (B) (C) …",
    "none": "(no label)",
}


def panel_label(idx: int, style: str, custom: str | None = None) -> str:
    """Return the label string for panel index *idx* in the chosen style.

    A custom non-empty string overrides *style*.
    """
    if custom:
        return custom
    if style == "A":   return chr(ord("A") + idx) if 0 <= idx < 26 else ""
    if style == "a":   return chr(ord("a") + idx) if 0 <= idx < 26 else ""
    if style == "1":   return str(idx + 1)
    if style == "I":   return _to_roman(idx + 1)
    if style == "i":   return _to_roman(idx + 1).lower()
    if style == "(A)": return f"({chr(ord('A') + idx)})" if 0 <= idx < 26 else ""
    return ""


def make_panel_figure(
    panels: list[dict],
    *,
    rows: int,
    cols: int,
    fig_width: float,
    fig_height: float,
    wspace: float = 0.30,
    hspace: float = 0.40,
    label_style: str = "A",
    label_fontsize: float = 16.0,
    label_fontweight: str = "bold",
    label_x_offset: float = -0.12,
    label_y_offset: float = 1.03,
) -> matplotlib.figure.Figure:
    """Build a Figure with `rows` × `cols` axes and draw each panel into its slot.

    Slots beyond `len(panels)` render as empty axes.
    """
    n_slots = rows * cols

    # The grid is created and laid out under the theme, matching what
    # plotter.make_figure does for a single plot. Each panel's own draw_plot
    # call re-applies the theme with that panel's typography, so panels can
    # differ from one another without leaking settings into their neighbours.
    with plot_style():
        fig = Figure(figsize=(fig_width, fig_height))
        axs = fig.subplots(rows, cols, squeeze=False)
        flat_axs = [ax for row in axs for ax in row]

        # First pass — draw plots (or hide axes for empty slots)
        for i in range(n_slots):
            ax = flat_axs[i]
            panel = panels[i] if i < len(panels) else {"mode": "empty"}
            mode = panel.get("mode", "empty")
            if mode == "empty":
                ax.set_axis_off()
                continue
            df = panel.get("df")
            cfg = dict(panel.get("config", {}))
            if df is None or df.empty:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                        transform=ax.transAxes, fontsize=12, color="gray")
                continue
            try:
                draw_plot(ax, df, **cfg)
            except Exception as e:
                # One broken panel must not cost the user the whole figure.
                ax.set_axis_off()
                ax.text(0.5, 0.5, f"Plot error:\n{e}", ha="center", va="center",
                        transform=ax.transAxes, fontsize=10, color="firebrick",
                        wrap=True)

        # Single tight_layout across the whole figure, then re-apply spacing.
        # The warning is captured rather than left on stderr so the app can
        # tell the user the grid is too small for its decorations.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.tight_layout()
        fig.layout_warning = any(
            "tight layout" in str(w.message).lower() for w in caught)
        fig.subplots_adjust(wspace=wspace, hspace=hspace)

    # Per-panel ylim/xlim — applied after tight_layout so it cannot re-expand them
    for i in range(n_slots):
        ax = flat_axs[i]
        panel = panels[i] if i < len(panels) else {}
        if panel.get("mode") == "plot":
            _apply_axis_limits(ax, ylim=panel.get("ylim"), xlim=panel.get("xlim"))

    # Panel labels — drawn last so they sit above everything else
    for i in range(n_slots):
        ax = flat_axs[i]
        panel = panels[i] if i < len(panels) else {}
        text = panel_label(i, label_style, custom=panel.get("label"))
        if not text:
            continue
        ax.text(label_x_offset, label_y_offset, text,
                transform=ax.transAxes,
                fontsize=label_fontsize,
                fontweight=label_fontweight,
                ha="left", va="bottom",
                clip_on=False)

    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_roman(n: int) -> str:
    if n <= 0 or n >= 4000:
        return str(n)
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out
