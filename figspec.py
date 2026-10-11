"""
figspec.py — translate a settings dict into ``plotter`` keyword arguments.

Every figure the app draws goes through here: the main preview, each slot of a
panel figure, and the batch "plot all sheets" export.  Previously each of those
built its own kwargs by hand, which is why batch export silently ignored axis
limits, line options and tick styling — it had simply never been updated.  One
builder keeps them in step.

The functions take a plain ``dict`` of ps_* values (from ``settings.snapshot()``
or a stored panel), never ``st.session_state``, so they stay testable and are
safe to call for a panel that is not the one currently being edited.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import utils


# ---------------------------------------------------------------------------
# Individual resolvers
# ---------------------------------------------------------------------------

def resolve_palette(s: dict, n: int) -> list[str]:
    """Colours for *n* treatments, honouring a custom palette when selected."""
    name = s.get("ps_palette_name", "iGEM")
    if name != "Custom":
        return utils.get_palette(name, n)

    custom = [c for c in (s.get("ps_custom_colors") or []) if c]
    if not custom:
        return utils.get_palette("iGEM", n)
    # Cycle rather than fall back wholesale: a partially filled custom palette
    # used to silently revert every colour to iGEM.
    return [custom[i % len(custom)] for i in range(n)]


def resolve_point_colors(s: dict, n: int) -> list[str] | None:
    """Per-treatment point colours, or None to keep the plot type's default."""
    custom = [c for c in (s.get("ps_point_colors") or []) if c]
    if not s.get("ps_point_custom") or not custom:
        return None
    return [custom[i % len(custom)] for i in range(n)]


def resolve_fonts(s: dict) -> tuple[dict | None, float, float | None]:
    """Return ``(fontsizes, font_scale, tick_fontsize)``.

    Per-element sizing wins over the global scale, and the Advanced tab's tick
    size overrides both — but only once moved off its default, which is how the
    control has always behaved.
    """
    if s.get("ps_font_mode") == "Per element":
        fontsizes: dict | None = {
            "title":      int(s.get("ps_fs_title", 14)),
            "axis_label": int(s.get("ps_fs_axis", 12)),
            "tick":       int(s.get("ps_fs_tick", 10)),
            "legend":     int(s.get("ps_fs_legend", 10)),
        }
        font_scale = 1.0
    else:
        fontsizes = None
        font_scale = float(s.get("ps_font_scale", 1.0))

    tick_adv = int(s.get("ps_tick_fontsize_adv", 10))
    if tick_adv != 10:
        tick_fs: float | None = float(tick_adv)
    elif fontsizes is not None:
        tick_fs = fontsizes.get("tick")
    else:
        tick_fs = None

    return fontsizes, font_scale, tick_fs


def parse_limit(value: Any) -> float | None:
    """``"1.5"`` → 1.5 ; blank or non-numeric → None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def axis_limits(s: dict) -> tuple[tuple | None, tuple | None]:
    """Return ``(ylim, xlim)``, each None when both bounds are blank."""
    ylim = (parse_limit(s.get("ps_ymin_str")), parse_limit(s.get("ps_ymax_str")))
    xlim = (parse_limit(s.get("ps_xmin_str")), parse_limit(s.get("ps_xmax_str")))
    return (
        None if all(v is None for v in ylim) else ylim,
        None if all(v is None for v in xlim) else xlim,
    )


def figure_size(s: dict) -> dict:
    return {
        "fig_width": float(s.get("ps_fig_width", 11)),
        "fig_height": float(s.get("ps_fig_height", 6)),
    }


def base_plot_type(s: dict) -> str:
    """``"bar+strip"`` → ``"bar"``."""
    return str(s.get("ps_plot_type", "bar+strip")).split("+")[0]


# ---------------------------------------------------------------------------
# The full kwarg set
# ---------------------------------------------------------------------------

def draw_kwargs(
    s: dict,
    *,
    n_treatments: int,
    title: str = "",
    ylabel: str = "Value",
    stat_results: pd.DataFrame | None = None,
) -> dict:
    """Build the kwargs for ``plotter.draw_plot`` from a settings dict."""
    fontsizes, font_scale, tick_fs = resolve_fonts(s)
    plot_type = base_plot_type(s)

    kwargs: dict[str, Any] = dict(
        plot_type=plot_type,
        error_bar=s.get("ps_error_bar", "sd"),
        cap_size=s.get("ps_cap_size", 0.08),
        show_points=s.get("ps_show_points", True),
        point_size=s.get("ps_point_size", 4.0),
        point_alpha=s.get("ps_point_alpha", 0.7),
        point_colors=resolve_point_colors(s, n_treatments),
        log_scale=s.get("ps_log_scale", False),
        show_grid=s.get("ps_show_grid", False),
        palette=resolve_palette(s, n_treatments),
        bar_edge_width=s.get("ps_bar_edge_width", 0.6),
        bar_edge_color=s.get("ps_bar_edge_color", "#000000"),
        bar_alpha=s.get("ps_bar_alpha", 1.0),
        bar_gap=s.get("ps_bar_gap", 0.0),
        title=title,
        xlabel=s.get("ps_xlabel", "Condition"),
        ylabel=ylabel,
        legend_title=s.get("ps_leg_title", "Treatment"),
        show_legend=s.get("ps_show_legend", True),
        legend_inside=s.get("ps_legend_inside", False),
        font_family=s.get("ps_font_family", "sans-serif"),
        font_scale=font_scale,
        fontsizes=fontsizes,
        tick_rotation=s.get("ps_tick_rotation", 40),
        tick_fontsize=tick_fs,
        spines=s.get("ps_spines", "open"),
        spine_width=s.get("ps_spine_width", 1.0),
        y_format=s.get("ps_y_format", "auto"),
        x_numeric=s.get("ps_x_numeric", "auto"),
        x_tick_interval=s.get("ps_x_tick_interval", 0.0),
        y_tick_interval=s.get("ps_y_tick_interval", 0.0),
        error_style=s.get("ps_error_style", "band"),
        line_width=s.get("ps_line_width", 1.5),
        marker_style=s.get("ps_marker_style", "o"),
        marker_size=s.get("ps_marker_size", 6.0),
        x_suffix=s.get("ps_x_suffix", ""),
        trendline=s.get("ps_trendline", "none"),
        trendline_source=s.get("ps_trendline_source", "means"),
        trendline_mode=s.get("ps_trendline_mode", "overlay"),
        sigmoids=[
            (c["alow"], c["ahigh"], c["p50"], c["dp"], c["color"])
            for c in (s.get("ps_sigmoids") or [])
        ],
        tick_direction=s.get("ps_tick_direction", "out"),
        major_tick_length=s.get("ps_major_tick_length", 4.0),
        major_tick_width=s.get("ps_major_tick_width", 0.8),
        minor_ticks_y=int(s.get("ps_minor_ticks_y", 0)),
        minor_ticks_x=int(s.get("ps_minor_ticks_x", 0)),
        minor_tick_length=s.get("ps_minor_tick_length", 2.0),
        minor_tick_width=s.get("ps_minor_tick_width", 0.6),
    )

    # Significance brackets are meaningless on a line plot and are never
    # produced for one, but guard anyway so a stale selection cannot leak in.
    if stat_results is not None and not stat_results.empty and plot_type != "line":
        kwargs.update(
            stat_results=stat_results,
            test_mode=s.get("ps_test_mode", "ttest"),
            compare_axis=s.get("ps_compare_axis", "conditions"),
            bracket_linewidth=s.get("ps_bracket_linewidth", 0.9),
            bracket_fontsize=s.get("ps_bracket_fontsize", 11.0),
            show_pvalue=s.get("ps_show_pvalue", False),
            show_significance=s.get("ps_show_significance", True),
            show_fold_change=s.get("ps_show_fold_change", False),
        )

    return kwargs


def export_kwargs(s: dict) -> dict:
    """Background options for ``utils.fig_to_bytes``."""
    return {
        "transparent": bool(s.get("ps_export_transparent", False)),
        "facecolor": s.get("ps_export_bg", "#FFFFFF"),
    }
